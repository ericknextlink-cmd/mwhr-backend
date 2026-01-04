from typing import List, Any, Optional
from datetime import datetime, timedelta
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlmodel import select, func, col, desc, asc, or_
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import selectinload # Import selectinload

from app.api import deps
from app.models.application import Application, ApplicationRead, ApplicationStatus, CertificateType, ApplicationReadAdmin
from app.models.user import User
from app.models.company_info import CompanyInfo, CompanyInfoRead
from app.models.director import DirectorRead
from app.models.document import DocumentRead
from app.services.audit_service import log_audit_event
from app.services.notification_service import notify_user
from app.services.storage_service import storage_service
from app.services.security_service import security_service
from app.core.config import settings

router = APIRouter()

# --- Response Models for Admin Details ---
class AdminApplicationDetails(ApplicationRead):
    company_info: Optional[CompanyInfoRead] = None
    directors: List[DirectorRead] = []
    documents: List[DocumentRead] = []
    reviewer_email: Optional[str] = None # For frontend display

# --- Existing Endpoints ---

@router.get("/stats")
async def get_admin_stats(
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_admin),
) -> Any:
    """
    Get application statistics for the admin dashboard.
    """
    # Total Applications
    total_query = select(func.count(col(Application.id)))
    total_result = await session.exec(total_query)
    total = total_result.one()

    # Pending (submitted, pending_payment, in_review)
    pending_query = select(func.count(col(Application.id))).where(
        col(Application.status).in_([
            ApplicationStatus.SUBMITTED, 
            ApplicationStatus.PENDING_PAYMENT, 
            ApplicationStatus.IN_REVIEW,
            ApplicationStatus.DRAFT # Consider draft applications also as pending initial action
        ])
    )
    pending_result = await session.exec(pending_query)
    pending = pending_result.one()

    # Approved
    approved_query = select(func.count(col(Application.id))).where(
        Application.status == ApplicationStatus.APPROVED
    )
    approved_result = await session.exec(approved_query)
    approved = approved_result.one()
    
    # Rejected
    rejected_query = select(func.count(col(Application.id))).where(
        Application.status == ApplicationStatus.REJECTED
    )
    rejected_result = await session.exec(rejected_query)
    rejected = rejected_result.one()

    # Breakdown by Certificate Type
    type_breakdown = {}
    try:
        type_query = select(Application.certificate_type, func.count(Application.id)).group_by(Application.certificate_type)
        type_result = await session.exec(type_query)
        # Ensure keys are raw string values (e.g. 'electrical', not 'CertificateType.ELECTRICAL')
        for row in type_result.all():
            key = row[0]
            if hasattr(key, "value"):
                key = key.value
            type_breakdown[str(key)] = row[1]
    except Exception as e:
        print(f"Error in type breakdown: {e}")
        # Continue without breakdown data rather than failing

    return {
        "total_applications": total,
        "pending_reviews": pending,
        "approved_certificates": approved,
        "rejected_applications": rejected,
        "type_breakdown": type_breakdown
    }

@router.get("/applications", response_model=List[ApplicationReadAdmin])
async def list_applications(
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_admin),
    skip: int = 0,
    limit: int = 100,
    status: ApplicationStatus | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    certificate_type: CertificateType | None = None,
    search: str | None = None,
    sort_by: str = "created_at",
    sort_desc: bool = True,
):
    """
    List all applications with optional status, date, type filtering and search.
    Includes Company Name and User Email.
    """
    query = select(Application).options(
        selectinload(Application.company_info),
        selectinload(Application.user)
    )
    
    # Optional Joins for Search
    if search:
        query = query.outerjoin(Application.company_info).join(Application.user)
        query = query.where(
            or_(
                CompanyInfo.company_name.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%")
            )
        )

    if status:
        query = query.where(Application.status == status)
    
    if certificate_type:
        query = query.where(Application.certificate_type == certificate_type)
    
    if start_date:
        query = query.where(Application.created_at >= start_date)
    
    if end_date:
        query = query.where(Application.created_at <= end_date)
    
    # Sorting
    if hasattr(Application, sort_by):
        sort_column = getattr(Application, sort_by)
    else:
        sort_column = Application.created_at

    if sort_desc:
        query = query.order_by(desc(sort_column))
    else:
        query = query.order_by(asc(sort_column))
    
    query = query.offset(skip).limit(limit)
    
    result = await session.exec(query)
    applications = result.all()
    
    admin_apps = []
    for app in applications:
        admin_app = ApplicationReadAdmin.from_orm(app)
        if app.company_info:
            admin_app.company_name = app.company_info.company_name
        if app.user:
            admin_app.user_email = app.user.email
        admin_apps.append(admin_app)
        
    return admin_apps

@router.get("/applications/{id}/details", response_model=AdminApplicationDetails)
async def get_application_details_for_admin(
    id: int,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_admin),
):
    """
    Get full details of a specific application for admin review, including company info, directors, and documents.
    """
    application = await session.exec(
        select(Application).where(Application.id == id).options(
            selectinload(Application.company_info),
            selectinload(Application.directors),
            selectinload(Application.documents),
            selectinload(Application.reviewer)
        )
    )
    result = application.first()

    if not result:
        raise HTTPException(status_code=404, detail="Application not found")
    
    # Manually populate AdminApplicationDetails to include reviewer_email
    # Since result is an Application object, we can convert it or just attach the field if Pydantic allows (it doesn't on ORM objects directly)
    # Better to create the response object explicitly.
    
    details = AdminApplicationDetails.from_orm(result)
    if result.reviewer:
        details.reviewer_email = result.reviewer.email
        
    return details

@router.patch("/applications/{id}/status", response_model=ApplicationRead)
async def update_application_status(
    id: int,
    status: ApplicationStatus, # Directly take the enum status
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_admin),
):
    """
    Approve or Reject an application.
    """
    application = await session.get(Application, id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    # Enforce Assignment Lock
    if application.assigned_to and application.assigned_to != current_user.id:
        raise HTTPException(status_code=403, detail="This application is assigned to another admin.")
    
    # Require assignment before action
    if not application.assigned_to:
        raise HTTPException(status_code=400, detail="Please assign this application to yourself before taking action.")
    
    # SECURITY/LOGIC: Prevent approval of incomplete applications
    if status == ApplicationStatus.APPROVED and application.status not in [ApplicationStatus.SUBMITTED, ApplicationStatus.IN_REVIEW, ApplicationStatus.SUSPENDED]:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot approve an incomplete application. Current status is '{application.status}'. Application must be submitted first."
        )

    application.status = status
    
    # Set expiry date if approved
    if status == ApplicationStatus.APPROVED:
        application.expiry_date = datetime.utcnow() + timedelta(days=365)
        
        # Set issued date only if not already set (first time approval)
        if not application.issued_date:
            application.issued_date = datetime.utcnow()
        
        # XSCNS Security Generation
        if not application.internal_uid:
             application.internal_uid = uuid.uuid4()
             
        if not application.certificate_number:
             sec_data = security_service.generate_certificate_number(
                 application.certificate_class, 
                 application.internal_uid
             )
             application.certificate_number = sec_data["full_number"]
             application.security_token = sec_data["token"]
        
    session.add(application)
    
    # Audit Log
    await log_audit_event(
        session,
        user_id=current_user.id,
        action=f"STATUS_UPDATE_{status.upper()}",
        target_type="application",
        target_id=application.id,
        target_label=f"Application #{application.id}", # Or maybe application.certificate_type?
        details=f"Status changed to {status}"
    )

    # Notify User
    await notify_user(
        session,
        user_id=application.user_id,
        title=f"Application {status.title()}",
        message=f"Your application #{application.id} for {application.certificate_type.replace('_', ' ').title()} has been {status}.",
        link=f"/dashboard?id={application.id}" # Or specific view
    )

    await session.commit()
    await session.refresh(application)
    return application

@router.get("/renewals/expiring", response_model=List[ApplicationRead])
async def get_expiring_certificates(
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_admin),
    days: int = 30,
):
    """
    List approved applications expiring within the next 'days' (default 30).
    """
    target_date = datetime.utcnow() + timedelta(days=days)
    
    query = select(Application).where(
        Application.status == ApplicationStatus.APPROVED,
        Application.expiry_date != None,
        Application.expiry_date <= target_date,
        Application.expiry_date >= datetime.utcnow() 
    ).order_by(Application.expiry_date.asc())
    
    result = await session.exec(query)
    return result.all()

@router.post("/applications/{id}/assign", response_model=ApplicationRead)
async def assign_application(
    id: int,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_admin),
):
    """
    Assign an application to the current admin.
    """
    application = await session.get(Application, id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    if application.assigned_to and application.assigned_to != current_user.id:
        # Check if current user is superadmin to override? Or just block.
        # For now, block unless superadmin.
        if not current_user.is_superuser:
             raise HTTPException(status_code=400, detail="Application is already assigned to another admin.")

    application.assigned_to = current_user.id
    session.add(application)
    
    await log_audit_event(
        session, user_id=current_user.id, action="APPLICATION_ASSIGNED",
        target_type="application", target_id=application.id, 
        target_label=f"Application #{application.id}",
        details=f"Assigned to {current_user.email}"
    )
    
    await session.commit()
    await session.refresh(application)
    return application

@router.post("/applications/{id}/unassign", response_model=ApplicationRead)
async def unassign_application(
    id: int,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_admin),
):
    """
    Unassign an application.
    """
    application = await session.get(Application, id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    if application.assigned_to != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="You cannot unassign an application assigned to someone else.")

    application.assigned_to = None
    session.add(application)
    
    await log_audit_event(
        session, user_id=current_user.id, action="APPLICATION_UNASSIGNED",
        target_type="application", target_id=application.id, 
        target_label=f"Application #{application.id}",
        details="Unassigned"
    )
    
    await session.commit()
    await session.refresh(application)
    return application

# --- Template Management Endpoints ---

@router.get("/templates", response_model=List[dict])
async def list_templates(
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_admin),
):
    """
    List all certificate templates in storage.
    Only accessible by Super Admins.
    """
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Only Super Admins can manage templates.")
    
    if not storage_service.client:
        raise HTTPException(status_code=500, detail="Storage not configured.")

    try:
        # List files in 'templates' folder
        res = storage_service.client.storage.from_(settings.SUPABASE_BUCKET_NAME).list("templates")
        return res
    except Exception as e:
        print(f"Error listing templates: {e}")
        raise HTTPException(status_code=500, detail="Failed to list templates.")

@router.post("/templates")
async def upload_template(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_admin),
):
    """
    Upload or overwrite a certificate template.
    Filename should match the certificate type (e.g., 'electrical.pdf').
    Only accessible by Super Admins.
    """
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Only Super Admins can manage templates.")

    if not storage_service.client:
        raise HTTPException(status_code=500, detail="Storage not configured.")
        
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")

    file_content = await file.read()
    file_path = f"templates/{file.filename}"

    try:
        # Upload using upsert to overwrite
        res = storage_service.client.storage.from_(settings.SUPABASE_BUCKET_NAME).upload(
            file_path,
            file_content,
            {"content-type": "application/pdf", "upsert": "true"} 
        )
        return {"message": f"Template {file.filename} uploaded successfully.", "path": file_path}
    except Exception as e:
        print(f"Error uploading template: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload template: {str(e)}")
