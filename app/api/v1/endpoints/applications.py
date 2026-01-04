from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import select, or_
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import selectinload

from app.api import deps
from app.models.application import Application, ApplicationCreate, ApplicationRead, ApplicationUpdate, ApplicationStatus
from app.models.user import User
from app.models.company_info import CompanyInfo
from app.models.director import Director
from app.models.document import Document
from app.services.certificate_generator import certificate_generator
from app.services.notification_service import notify_admins
from app.services.otp_store import otp_store

router = APIRouter()

class ApplicationVerifyResponse(BaseModel):
    id: int
    status: str
    certificate_type: str
    company_name: str
    expiry_date: datetime | None
    company_address: str | None

class OTPRequest(BaseModel):
    phone_number: str

class OTPVerify(BaseModel):
    phone_number: str
    otp: str

class OTPResponse(BaseModel):
    message: str
    token: Optional[str] = None

@router.post("/public/otp/send")
async def send_otp(payload: OTPRequest):
    """Generate and 'send' OTP (Logs to console)."""
    if not payload.phone_number:
         raise HTTPException(status_code=400, detail="Phone number required")
    otp = otp_store.generate_otp(payload.phone_number)
    print(f"------------ OTP ALERT ------------")
    print(f"OTP for {payload.phone_number}: {otp}")
    print(f"-----------------------------------")
    return {"message": "OTP sent successfully"}

@router.post("/public/otp/verify", response_model=OTPResponse)
async def verify_otp_code(payload: OTPVerify):
    """Verify OTP and return access token."""
    token = otp_store.verify_otp(payload.phone_number, payload.otp)
    if not token:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    return {"message": "Verified", "token": token}

@router.get("/public/verify/{identifier}", response_model=ApplicationVerifyResponse)
async def verify_certificate(
    identifier: str,
    token: str,
    session: AsyncSession = Depends(deps.get_session),
):
    """
    Public endpoint to verify a certificate by Application ID, Certificate Number, or Security Token.
    Requires a valid verification token from OTP flow.
    """
    # Verify Token
    if not otp_store.is_token_valid(token):
        raise HTTPException(status_code=401, detail="Verification session expired. Please verify phone number again.")

    # Fetch application with company info
    # Search by Certificate Number OR Security Token OR ID (if numeric)
    conditions = [
        Application.certificate_number == identifier,
        Application.security_token == identifier
    ]
    if identifier.isdigit():
        conditions.append(Application.id == int(identifier))
        
    query = select(Application).where(or_(*conditions)).options(selectinload(Application.company_info))
    result = await session.exec(query)
    application = result.first()

    if not application:
        raise HTTPException(status_code=404, detail="Certificate not found")
    
    # Only return if Approved, Suspended, or Cancelled (Revoked)
    # Hide Draft/In Review to prevent enumeration
    allowed_statuses = [
        ApplicationStatus.APPROVED, 
        ApplicationStatus.SUSPENDED, 
        ApplicationStatus.CANCELLED,
        ApplicationStatus.REJECTED # Optional: if you want to show 'Revoked' for rejected renewals?
    ]

    if application.status not in allowed_statuses:
         raise HTTPException(status_code=404, detail="Certificate not found or not valid")

    return {
        "id": application.id,
        "status": application.status,
        "certificate_type": application.certificate_type,
        "company_name": application.company_info.company_name if application.company_info else "Unknown",
        "company_address": application.company_info.address if application.company_info else "Unknown",
        "expiry_date": application.expiry_date
    }

@router.get("/{id}/certificate")
async def generate_certificate(
    id: int,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
):
    """
    Generate and download the classification certificate.
    Only available for approved applications.
    """
    # Fetch app with company info
    query = select(Application).where(Application.id == id).options(selectinload(Application.company_info))
    result = await session.exec(query)
    application = result.first()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    # Check permissions
    if not current_user.is_superuser and (application.user_id != current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")

    if application.status == ApplicationStatus.SUSPENDED:
        raise HTTPException(status_code=400, detail="This certificate has been suspended. Please contact support.")

    if application.status != "approved":
        raise HTTPException(status_code=400, detail="Certificate is only available for approved applications.")

    if not application.company_info:
        raise HTTPException(status_code=400, detail="Company information missing.")

    # Generate PDF
    pdf_buffer = certificate_generator.generate(application, application.company_info.company_name)
    
    # NEW FILENAME FORMAT: CompanyName_Type_Class_CertificateNumber.pdf
    company_clean = application.company_info.company_name.replace(" ", "_")
    type_clean = application.certificate_type.replace(" ", "_")
    class_clean = (application.certificate_class or "N/A").replace(" ", "_")
    
    filename = f"{company_clean}_{type_clean}_{class_clean}_{application.id}.pdf"

    return StreamingResponse(
        pdf_buffer, 
        media_type="application/pdf", 
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.post("/", response_model=ApplicationRead)
async def create_application(
    *,
    session: AsyncSession = Depends(deps.get_session),
    application_in: ApplicationCreate,
    current_user: User = Depends(deps.get_current_user),
):
    """
    Create a new application.
    """
    # Check for existing active applications of the same type
    existing_app_query = select(Application).where(
        Application.user_id == current_user.id,
        Application.certificate_type == application_in.certificate_type,
        Application.status != ApplicationStatus.REJECTED, # Allow re-applying if rejected
        Application.status != ApplicationStatus.CANCELLED # Allow re-applying if cancelled
    )
    existing_apps = await session.exec(existing_app_query)
    if existing_apps.first():
        raise HTTPException(
            status_code=400, 
            detail=f"You already have an active application for {application_in.certificate_type.value.replace('_', ' ').title()}."
        )

    application = Application.from_orm(application_in)
    application.user_id = current_user.id
    session.add(application)
    await session.commit()
    await session.refresh(application)
    return application

@router.get("/", response_model=List[ApplicationRead])
async def read_applications(
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
    skip: int = 0,
    limit: int = 100,
):
    """
    Retrieve applications.
    """
    if current_user.is_superuser:
        statement = select(Application).options(selectinload(Application.company_info), selectinload(Application.user)).order_by(Application.created_at.desc()).offset(skip).limit(limit)
    else:
        statement = select(Application).where(Application.user_id == current_user.id).options(selectinload(Application.company_info), selectinload(Application.user)).order_by(Application.created_at.desc()).offset(skip).limit(limit)
        
    applications = await session.exec(statement)
    results = applications.all()
    
    # Convert to Pydantic objects for clean serialization
    read_results = [ApplicationRead.model_validate(app) for app in results]
    
    # Manually populate company_name and user_email for the response
    for i, app in enumerate(results):
        try:
            # Safely check for company_info from the database record
            if hasattr(app, 'company_info') and app.company_info:
                read_results[i].company_name = app.company_info.company_name
            # Safely check for user from the database record
            if hasattr(app, 'user') and app.user:
                read_results[i].user_email = app.user.email
        except Exception as e:
            print(f"DEBUG: Error processing application data for ID {app.id if hasattr(app, 'id') else 'unknown'}: {e}")
            
    return read_results

class BulkPaymentRequest(BaseModel):
    application_ids: List[int]

@router.post("/pay", response_model=List[ApplicationRead])
async def bulk_pay_applications(
    *,
    session: AsyncSession = Depends(deps.get_session),
    payment_in: BulkPaymentRequest,
    current_user: User = Depends(deps.get_current_user),
):
    """
    Process bulk payment for multiple applications.
    Simulates payment processing and updates status to DRAFT (Step 4).
    """
    print(f"DEBUG: Bulk Payment Request: {payment_in} from user {current_user.id}")
    updated_apps = []
    
    # Verify all apps belong to user
    stmt = select(Application).where(Application.id.in_(payment_in.application_ids))
    result = await session.exec(stmt)
    applications = result.all()
    
    print(f"DEBUG: Found {len(applications)} apps. Requested {len(payment_in.application_ids)}")

    if len(applications) != len(payment_in.application_ids):
        # Identify missing IDs
        found_ids = {app.id for app in applications}
        missing_ids = set(payment_in.application_ids) - found_ids
        print(f"DEBUG: Missing IDs: {missing_ids}")
        raise HTTPException(status_code=404, detail=f"One or more applications not found: {missing_ids}")

    for app in applications:
        if app.user_id != current_user.id:
            print(f"DEBUG: Permission denied for App {app.id}. Owner: {app.user_id}, Requester: {current_user.id}")
            raise HTTPException(status_code=403, detail=f"Permission denied for application #{app.id}")
        
        # Check if payable (Must be Draft or Pending Payment)
        if app.status not in [ApplicationStatus.DRAFT, ApplicationStatus.PENDING_PAYMENT]:
             raise HTTPException(
                status_code=400, 
                detail=f"Application #{app.id} cannot be paid for. Current status: {app.status}"
            )
        
        # Check if already paid (Step 4 starts Company Info, implying Payment (Step 3) is done)
        if app.current_step >= 4:
             raise HTTPException(
                status_code=400, 
                detail=f"Application #{app.id} is already paid."
            )

        # Update status and step
        # Set to DRAFT to allow user to continue editing (Company Info)
        app.status = ApplicationStatus.DRAFT
        app.current_step = 4
            
        session.add(app)
        updated_apps.append(app)

    await session.commit()
    
    for app in updated_apps:
        await session.refresh(app)
        
    return updated_apps

@router.get("/{id}", response_model=ApplicationRead)
async def read_application(
    *,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
    id: int,
):
    """
    Get application by ID.
    """
    application = await session.get(Application, id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    if not current_user.is_superuser and (application.user_id != current_user.id):
        raise HTTPException(status_code=400, detail="Not enough permissions")
    return application

@router.patch("/{id}", response_model=ApplicationRead)
async def update_application(
    *,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
    id: int,
    application_in: ApplicationUpdate,
):
    """
    Update an application.
    """
    application = await session.get(Application, id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    if not current_user.is_superuser and (application.user_id != current_user.id):
        raise HTTPException(status_code=400, detail="Not enough permissions")
        
    print(f"DEBUG: Payload received: {application_in}")
    print(f"DEBUG: Status in payload: {application_in.status}")
    
    # 1. Capture old status for comparison
    old_status = application.status
    
    # 2. Get update data (exclude_unset=True allows partial updates)
    application_data = application_in.dict(exclude_unset=True)
    print(f"DEBUG: Dict to update: {application_data}")

    # 3. Explicitly handle status update with Enum conversion
    if "status" in application_data:
        new_status_str = application_data.pop("status") # Remove from dict so loop doesn't double-process
        if new_status_str:
            try:
                 application.status = ApplicationStatus(new_status_str)
            except ValueError:
                 raise HTTPException(status_code=400, detail=f"Invalid status: {new_status_str}")

    # 4. Update other fields
    for key, value in application_data.items():
        setattr(application, key, value)

    session.add(application)

    # 5. Check for status change to SUBMITTED and notify
    if application.status == ApplicationStatus.SUBMITTED and old_status != ApplicationStatus.SUBMITTED:
        # VALIDATION: Check completeness before allowing submission
        
        # Check Company Info
        company_info_result = await session.exec(select(CompanyInfo).where(CompanyInfo.application_id == id))
        if not company_info_result.first():
             raise HTTPException(status_code=400, detail="Cannot submit: Company Information is missing.")
             
        # Check Directors
        directors_result = await session.exec(select(Director).where(Director.application_id == id))
        if not directors_result.first():
             raise HTTPException(status_code=400, detail="Cannot submit: Directors Information is missing.")
             
        # Check Documents
        documents_result = await session.exec(select(Document).where(Document.application_id == id))
        if not documents_result.first():
             raise HTTPException(status_code=400, detail="Cannot submit: Supporting Documents are missing.")

        # Notify Admins (notify_admins NO LONGER commits)
        await notify_admins(
            session, 
            "New Application Submitted", 
            f"Application #{application.id} has been submitted by {current_user.email}.", 
            link=f"/admin/applications/{application.id}"
        )

    await session.commit()
    await session.refresh(application)
    return application

@router.post("/{id}/renew", response_model=ApplicationRead)
async def renew_application(
    *,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
    id: int,
):
    """
    Renew an existing approved application.
    Creates a new DRAFT application with cloned data (Company Info, Directors).
    """
    # Fetch original application with related data
    query = select(Application).where(Application.id == id).options(
        selectinload(Application.company_info),
        selectinload(Application.directors)
    )
    result = await session.exec(query)
    original_app = result.first()

    if not original_app:
        raise HTTPException(status_code=404, detail="Application not found")
    
    if original_app.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    if original_app.status != ApplicationStatus.APPROVED:
        raise HTTPException(status_code=400, detail="Only approved applications can be renewed.")

    # Create new Application
    new_app = Application(
        certificate_type=original_app.certificate_type,
        certificate_class=original_app.certificate_class,
        description=f"Renewal of Application #{original_app.id}",
        status=ApplicationStatus.DRAFT,
        current_step=4, # Start at Company Info step (Step 4), skipping Apply/Select Class/Payment(if applicable)
        user_id=current_user.id
    )
    session.add(new_app)
    await session.commit() # Commit to get new_app.id

    # Clone Company Info
    if original_app.company_info:
        new_company_info = CompanyInfo(
            company_name=original_app.company_info.company_name,
            registration_number=original_app.company_info.registration_number,
            phone=original_app.company_info.phone,
            address=original_app.company_info.address,
            business_type=original_app.company_info.business_type,
            application_id=new_app.id # Link to new app
        )
        session.add(new_company_info)

    # Clone Directors
    for director in original_app.directors:
        new_director = Director(
            name=director.name,
            position=director.position,
            nationality=director.nationality,
            application_id=new_app.id # Link to new app
        )
        session.add(new_director)

    await session.commit()
    await session.refresh(new_app)
    return new_app

@router.post("/{id}/cancel", response_model=ApplicationRead)
async def cancel_application(
    *,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
    id: int,
):
    """
    Cancel an application.
    Only allows cancellation if status is DRAFT, PENDING_PAYMENT, or SUBMITTED.
    """
    application = await session.get(Application, id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    if application.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    # Allow cancellation for these statuses
    cancellable_statuses = [
        ApplicationStatus.DRAFT, 
        ApplicationStatus.SUBMITTED, 
        ApplicationStatus.PENDING_PAYMENT,
        ApplicationStatus.IN_REVIEW
    ]
    
    if application.status not in cancellable_statuses:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot cancel application in '{application.status}' status."
        )

    application.status = ApplicationStatus.CANCELLED
    session.add(application)
    await session.commit()
    await session.refresh(application)
    return application