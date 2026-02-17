import uuid
from typing import List, Optional
from datetime import datetime, timezone
from io import BytesIO
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import select, or_
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import selectinload

from app.api import deps
from app.models.application import Application, ApplicationCreate, ApplicationRead, ApplicationReadForApplicant, ApplicationUpdate, ApplicationStatus, CertificateType, HIGHEST_CLASS_BY_TYPE
from app.models.user import User
from app.models.company_info import CompanyInfo
from app.models.director import Director
from app.models.document import Document
from app.core.security import create_renewal_token, decode_renewal_token, verify_password
from app.services.certificate_generator import certificate_generator
from app.services.invoice_pdf_generator import invoice_pdf_generator
from app.services.notification_service import notify_admins
from app.services.otp_store import otp_store
from app.services.storage_service import storage_service
from app.services.email_service import send_invoice_email

router = APIRouter()


class RenewFromTokenRequest(BaseModel):
    token: str

class ApplicationVerifyResponse(BaseModel):
    id: str  # UUID (internal_uid)
    status: str
    certificate_type: str
    certificate_number: str | None
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

class ApplicationDetailsResponse(BaseModel):
    id: str  # UUID (internal_uid)
    certificate_type: str
    certificate_class: Optional[str] = None
    description: Optional[str] = None
    status: str
    current_step: int
    created_at: datetime
    updated_at: datetime
    company_info: Optional[dict] = None
    directors: List[dict] = []
    documents: List[dict] = []

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
    # Search by Certificate Number OR Security Token OR numeric ID OR UUID (internal_uid)
    conditions = [
        Application.certificate_number == identifier,
        Application.security_token == identifier
    ]
    if identifier.isdigit():
        conditions.append(Application.id == int(identifier))
    try:
        uid = uuid.UUID(identifier)
        conditions.append(Application.internal_uid == uid)
    except (ValueError, TypeError):
        pass
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
        "id": str(application.internal_uid),
        "status": application.status,
        "certificate_type": application.certificate_type,
        "certificate_number": application.certificate_number,
        "company_name": application.company_info.company_name if application.company_info else "Unknown",
        "company_address": application.company_info.address if application.company_info else "Unknown",
        "expiry_date": application.expiry_date,
    }


def _certificate_filename(application: Application) -> str:
    """Friendly filename: applicationtype-classtype-certificate.pdf (e.g. electrical-E1-certificate.pdf)."""
    type_clean = (application.certificate_type.value if hasattr(application.certificate_type, "value") else str(application.certificate_type)).replace(" ", "-").lower()
    class_clean = (application.certificate_class or "N/A").replace(" ", "-").strip() or "N/A"
    return f"{type_clean}-{class_clean}-certificate.pdf"


def _invoice_filename(application: Application, invoice_number: str) -> str:
    """Friendly filename: applicationtype-classtype-invoicenumber.pdf (e.g. electrical-E1-INV-2026-000214.pdf)."""
    type_clean = (application.certificate_type.value if hasattr(application.certificate_type, "value") else str(application.certificate_type)).replace(" ", "-").lower()
    class_clean = (application.certificate_class or "N/A").replace(" ", "-").strip() or "N/A"
    return f"{type_clean}-{class_clean}-{invoice_number}.pdf"


async def _build_certificate_response(
    application: Application,
    session: AsyncSession,
    *,
    owner_password: str | None = None,
) -> tuple[Application, str, StreamingResponse]:
    """
    Generate or serve certificate PDF. PDF is viewable without a password; editing/copying
    is protected by owner password (user's account password when provided, else CERTIFICATE_OWNER_PASSWORD from env).
    """
    from app.core.config import settings

    filename = _certificate_filename(application)
    cert_path = f"applications/{application.id}/certifications/{filename}"

    now_utc = datetime.now(timezone.utc)
    app_expiry = application.expiry_date
    if app_expiry and getattr(app_expiry, "tzinfo", None) is None:
        app_expiry = app_expiry.replace(tzinfo=timezone.utc)
    is_expired = bool(application.expiry_date and app_expiry and app_expiry < now_utc)
    renewal_token = create_renewal_token(str(application.internal_uid))

    pdf_owner_password = owner_password or getattr(settings, "CERTIFICATE_OWNER_PASSWORD", None) or "mwhwr-cert-secure"
    existing_pdf = None if (is_expired or owner_password) else storage_service.download_file(cert_path)
    if existing_pdf:
        return (application, filename, StreamingResponse(
            BytesIO(existing_pdf),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        ))

    pdf_buffer, pdf_hash = certificate_generator.generate(
        application,
        application.company_info.company_name,
        renewal_token=renewal_token,
        is_expired=is_expired,
        certificate_owner_password=pdf_owner_password,
    )
    if not application.certificate_pdf_hash:
        application.certificate_pdf_hash = pdf_hash
        session.add(application)
        await session.commit()

    pdf_bytes = pdf_buffer.getvalue()
    storage_service.upload_certificate(pdf_bytes, application.id, filename)
    pdf_buffer.seek(0)
    return (application, filename, StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    ))


@router.get("/public/certificate/{identifier}")
async def download_certificate_public(
    identifier: str,
    token: str,
    account_password: str | None = None,
    session: AsyncSession = Depends(deps.get_session),
):
    """
    Public certificate download after OTP verification. Use same identifier as verify.
    Optional account_password: if provided and matches the certificate owner's account password,
    that password is used as the PDF owner (edit) password; otherwise CERTIFICATE_OWNER_PASSWORD from env is used.
    """
    if not otp_store.is_token_valid(token):
        raise HTTPException(status_code=401, detail="Verification session expired. Please verify phone number again.")

    conditions = [
        Application.certificate_number == identifier,
        Application.security_token == identifier,
    ]
    if identifier.isdigit():
        conditions.append(Application.id == int(identifier))
    try:
        uid = uuid.UUID(identifier)
        conditions.append(Application.internal_uid == uid)
    except (ValueError, TypeError):
        pass
    query = select(Application).where(or_(*conditions)).options(
        selectinload(Application.company_info),
        selectinload(Application.user),
    )
    result = await session.exec(query)
    application = result.first()

    if not application:
        raise HTTPException(status_code=404, detail="Certificate not found")
    if application.status != ApplicationStatus.APPROVED and application.status != ApplicationStatus.SUSPENDED:
        raise HTTPException(status_code=404, detail="Certificate not available for download")
    if not application.company_info:
        raise HTTPException(status_code=400, detail="Company information missing.")

    owner_pwd: str | None = None
    if account_password and application.user and verify_password(account_password, application.user.hashed_password):
        owner_pwd = account_password
    _, _, response = await _build_certificate_response(application, session, owner_password=owner_pwd)
    return response


@router.get("/{application_uid}/certificate")
async def generate_certificate(
    application_uid: uuid.UUID,
    account_password: str | None = None,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
):
    """
    Generate and download the classification certificate. PDF can be viewed without a password;
    editing/copying is protected by owner password. Optional account_password: if provided and
    matches the logged-in user's password, that password is used as the PDF owner (edit) password;
    otherwise the system uses CERTIFICATE_OWNER_PASSWORD from env.
    """
    application = await deps.get_application_by_uid(session, application_uid)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    result = await session.exec(
        select(Application).where(Application.id == application.id).options(selectinload(Application.company_info))
    )
    application = result.one()
    if not current_user.is_superuser and (application.user_id != current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")

    if application.status == ApplicationStatus.SUSPENDED:
        raise HTTPException(status_code=400, detail="This certificate has been suspended. Please contact support.")

    if application.status != "approved":
        raise HTTPException(status_code=400, detail="Certificate is only available for approved applications.")

    if not application.company_info:
        raise HTTPException(status_code=400, detail="Company information missing.")

    owner_pwd: str | None = None
    if account_password and verify_password(account_password, current_user.hashed_password):
        owner_pwd = account_password
    _, _, response = await _build_certificate_response(application, session, owner_password=owner_pwd)
    return response


async def _resolve_application_for_invoice(
    session: AsyncSession, application_id_or_uid: str
) -> Optional[Application]:
    """Resolve application by UUID or legacy integer id (for backward compatibility)."""
    try:
        uid = uuid.UUID(application_id_or_uid)
        return await deps.get_application_by_uid(session, uid)
    except (ValueError, TypeError):
        pass
    if application_id_or_uid.isdigit():
        return await session.get(Application, int(application_id_or_uid))
    return None


@router.get("/{application_id_or_uid}/invoice")
async def get_invoice_pdf(
    application_id_or_uid: str,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
):
    """
    Download the 2-page invoice PDF (letter + invoice) generated after payment.
    Accepts application UUID or legacy integer id. Only for the application owner or superuser.
    If the invoice is not in storage but the application is paid (step >= 4), it is generated
    on-demand, uploaded, and returned so users can always get their invoice.
    """
    application = await _resolve_application_for_invoice(session, application_id_or_uid)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    if not current_user.is_superuser and application.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    # Prefer friendly filename (applicationtype-classtype-invoicenumber.pdf); fallback to legacy invoice.pdf
    invoice_num = getattr(application, "invoice_number", None)
    if invoice_num:
        filename = _invoice_filename(application, invoice_num)
    else:
        filename = "invoice.pdf"
    path = f"applications/{application.id}/invoices/{filename}"
    pdf_bytes = storage_service.download_file(path)
    if not pdf_bytes and filename != "invoice.pdf":
        path = f"applications/{application.id}/invoices/invoice.pdf"
        pdf_bytes = storage_service.download_file(path)
        if pdf_bytes:
            filename = "invoice.pdf"
    if not pdf_bytes:
        # File missing in storage (e.g. deleted or never uploaded): generate on-demand and return it
        print(f"Invoice not in storage for application {application.id} (uid={application.internal_uid}); generating on-demand.")
        try:
            result = await session.exec(
                select(Application).where(Application.id == application.id).options(
                    selectinload(Application.company_info),
                )
            )
            app_with_company = result.one_or_none()
            if not app_with_company:
                raise HTTPException(status_code=404, detail="Application not found.")
            pdf_buffer, invoice_number = invoice_pdf_generator.generate(
                app_with_company, app_with_company.company_info
            )
            pdf_bytes = pdf_buffer.getvalue()
            if not pdf_bytes:
                raise HTTPException(status_code=500, detail="Generated invoice was empty.")
            app_with_company.invoice_number = invoice_number
            filename = _invoice_filename(app_with_company, invoice_number)
            session.add(app_with_company)
            await session.commit()
            try:
                storage_service.upload_invoice(pdf_bytes, application.id, filename)
            except Exception as e:
                print(f"On-demand invoice generated but upload failed for app {application.id}: {e}")
            print(f"On-demand invoice generated successfully for application {application.id}, returning PDF.")
        except HTTPException:
            raise
        except Exception as e:
            import traceback
            print(f"On-demand invoice generation failed for application {application.id}: {e}")
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail=f"Invoice could not be generated: {e!s}",
            )
    if not pdf_bytes:
        raise HTTPException(status_code=404, detail="Invoice not found. It is generated after payment.")
    # Use quoted filename for Content-Disposition in case it contains special chars
    safe_name = filename.replace('"', "%22")
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


@router.get("/reusable", response_model=List[ApplicationRead])
async def get_reusable_applications(
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
):
    """
    Get previous applications that have complete data (company info, directors, documents)
    that can be reused for new applications.
    Only returns applications with status: submitted, in_review, approved
    """
    from app.models.company_info import CompanyInfo
    from app.models.director import Director
    from app.models.document import Document
    
    # Get applications with complete data
    statement = (
        select(Application)
        .where(
            Application.user_id == current_user.id,
            Application.status.in_([
                ApplicationStatus.SUBMITTED,
                ApplicationStatus.IN_REVIEW,
                ApplicationStatus.APPROVED
            ])
        )
        .options(
            selectinload(Application.company_info),
            selectinload(Application.directors),
            selectinload(Application.documents)
        )
        .order_by(Application.created_at.desc())
    )
    
    applications = await session.exec(statement)
    results = applications.all()
    
    # Filter to only include applications with complete data
    reusable = []
    for app in results:
        has_company = app.company_info is not None
        has_directors = len(app.directors) > 0
        has_documents = len(app.documents) > 0
        
        if has_company and has_directors and has_documents:
            reusable.append(app)
    
    return [
        ApplicationRead.from_application(
            app,
            company_name=app.company_info.company_name if app.company_info else None,
            user_email=app.user.email if app.user else None,
        )
        for app in reusable
    ]

class CloneApplicationRequest(BaseModel):
    source_application_id: str  # UUID (internal_uid)

@router.post("/{application_uid}/clone", response_model=ApplicationRead)
async def clone_application_data(
    application_uid: uuid.UUID,
    *,
    session: AsyncSession = Depends(deps.get_session),
    clone_request: CloneApplicationRequest,
    current_user: User = Depends(deps.get_current_user),
):
    """
    Clone data (company info, directors, documents) from a previous application
    to the current application. This allows users to reuse data from previous applications.
    """
    from app.models.company_info import CompanyInfo
    from app.models.director import Director
    from app.models.document import Document
    from app.services.storage_service import storage_service
    
    target_app = await deps.get_application_by_uid(session, application_uid)
    if not target_app:
        raise HTTPException(status_code=404, detail="Target application not found")
    if target_app.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    try:
        source_uid = uuid.UUID(clone_request.source_application_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid source application ID format")
    source_app = await deps.get_application_by_uid(session, source_uid)
    if not source_app:
        raise HTTPException(status_code=404, detail="Source application not found")
    if source_app.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    if source_app.id == target_app.id:
        raise HTTPException(status_code=400, detail="Cannot clone from the same application")
    
    # Load source application data
    source_company_query = select(CompanyInfo).where(
        CompanyInfo.application_id == source_app.id
    )
    source_company_result = await session.exec(source_company_query)
    source_company = source_company_result.first()
    
    source_directors_query = select(Director).where(
        Director.application_id == source_app.id
    )
    source_directors_result = await session.exec(source_directors_query)
    source_directors = source_directors_result.all()
    
    source_documents_query = select(Document).where(
        Document.application_id == source_app.id
    )
    source_documents_result = await session.exec(source_documents_query)
    source_documents = source_documents_result.all()
    
    if not source_company:
        raise HTTPException(status_code=400, detail="Source application has no company information")
    if len(source_directors) == 0:
        raise HTTPException(status_code=400, detail="Source application has no directors")
    if len(source_documents) == 0:
        raise HTTPException(status_code=400, detail="Source application has no documents")
    
    # Clone company info
    existing_target_company = await session.exec(
        select(CompanyInfo).where(CompanyInfo.application_id == target_app.id)
    )
    if existing_target_company.first():
        # Update existing
        target_company = existing_target_company.first()
        target_company.company_name = source_company.company_name
        target_company.registration_number = source_company.registration_number
        target_company.address = source_company.address
        target_company.city = source_company.city
        target_company.country = source_company.country
        target_company.phone_number = source_company.phone_number
        target_company.email = source_company.email
    else:
        # Create new
        target_company = CompanyInfo(
            application_id=target_app.id,
            company_name=source_company.company_name,
            registration_number=source_company.registration_number,
            address=source_company.address,
            city=source_company.city,
            country=source_company.country,
            phone_number=source_company.phone_number,
            email=source_company.email
        )
        session.add(target_company)
    
    # Clone directors (delete existing first, then add new)
    existing_target_directors = await session.exec(
        select(Director).where(Director.application_id == target_app.id)
    )
    for existing_dir in existing_target_directors.all():
        await session.delete(existing_dir)
    
    for source_dir in source_directors:
        new_director = Director(
            application_id=target_app.id,
            name=source_dir.name,
            position=source_dir.position,
            nationality=source_dir.nationality,
            phone_number=source_dir.phone_number,
            email=source_dir.email
        )
        session.add(new_director)
    
    # Clone documents (copy files in storage, create new document records)
    existing_target_docs = await session.exec(
        select(Document).where(Document.application_id == target_app.id)
    )
    for existing_doc in existing_target_docs.all():
        # Delete old file from storage
        if existing_doc.file_url:
            try:
                storage_service.delete_file(existing_doc.file_url)
            except Exception as e:
                print(f"Warning: Failed to delete old document file {existing_doc.file_url}: {e}")
        await session.delete(existing_doc)
    
    # Copy document files and create new records
    for source_doc in source_documents:
        # Copy file in storage (download and re-upload to new location)
        try:
            # Download source file
            source_file_data = storage_service.download_file(source_doc.file_url)
            if source_file_data:
                # Create UploadFile-like object from source file data
                from io import BytesIO
                from fastapi import UploadFile
                
                file_obj = BytesIO(source_file_data)
                file_obj.name = source_doc.filename
                
                # Create UploadFile wrapper
                upload_file = UploadFile(
                    filename=source_doc.filename,
                    file=file_obj
                )
                
                # Upload to target application folder: applications/{id}/documents/
                new_storage_path = await storage_service.upload_file(upload_file, target_app.id)
                
                # Create new document record
                new_document = Document(
                    application_id=target_app.id,
                    document_type=source_doc.document_type,
                    filename=source_doc.filename,
                    file_url=new_storage_path
                )
                session.add(new_document)
        except Exception as e:
            print(f"Warning: Failed to clone document {source_doc.filename}: {e}")
            # Continue with other documents
    
    # Update application step to 7 (Review) since data is complete
    target_app.current_step = 7
    session.add(target_app)
    
    await session.commit()
    await session.refresh(target_app)
    company_name = target_company.company_name if target_company else None
    return ApplicationRead.from_application(
        target_app, company_name=company_name, user_email=current_user.email
    )

@router.post("/", response_model=ApplicationRead)
async def create_application(
    *,
    session: AsyncSession = Depends(deps.get_session),
    application_in: ApplicationCreate,
    current_user: User = Depends(deps.get_current_user),
):
    """
    Create a new application. Same certificate type allowed only when upgrading (existing app not at highest class).
    """
    existing_app_query = select(Application).where(
        Application.user_id == current_user.id,
        Application.certificate_type == application_in.certificate_type,
        Application.status != ApplicationStatus.REJECTED,
        Application.status != ApplicationStatus.CANCELLED,
    )
    existing_apps_result = await session.exec(existing_app_query)
    existing_same_type = existing_apps_result.all()
    if existing_same_type:
        highest = HIGHEST_CLASS_BY_TYPE.get(application_in.certificate_type)
        has_highest = any(
            (app.certificate_class or "").strip().upper() == (highest or "").strip().upper()
            for app in existing_same_type
        )
        if has_highest:
            raise HTTPException(
                status_code=400,
                detail=f"You already have the highest class for this certificate type. No further application for {application_in.certificate_type.value.replace('_', ' ').title()}."
            )

    application = Application.model_validate(application_in)
    application.user_id = current_user.id
    session.add(application)
    await session.commit()
    await session.refresh(application)
    return ApplicationRead.from_application(application, user_email=current_user.email)

@router.get("/", response_model=List[ApplicationRead] | List[ApplicationReadForApplicant])
async def read_applications(
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
    skip: int = 0,
    limit: int = 100,
):
    """
    Retrieve applications. Applicants get ApplicationReadForApplicant (no assigned_to); admins get ApplicationRead.
    """
    if current_user.is_superuser:
        statement = select(Application).options(selectinload(Application.company_info), selectinload(Application.user)).order_by(Application.created_at.desc()).offset(skip).limit(limit)
    else:
        statement = select(Application).where(Application.user_id == current_user.id).options(selectinload(Application.company_info), selectinload(Application.user)).order_by(Application.created_at.desc()).offset(skip).limit(limit)

    applications = await session.exec(statement)
    results = applications.all()

    def company_name(app: Application): return app.company_info.company_name if getattr(app, "company_info", None) else None
    def user_email(app: Application): return app.user.email if getattr(app, "user", None) else None

    if current_user.is_superuser:
        return [
            ApplicationRead.from_application(app, company_name=company_name(app), user_email=user_email(app))
            for app in results
        ]
    return [
        ApplicationReadForApplicant.from_application(app, company_name=company_name(app), user_email=user_email(app))
        for app in results
    ]

class BulkPaymentRequest(BaseModel):
    application_ids: List[str]  # UUIDs (internal_uid)

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
    
    uids = []
    for sid in payment_in.application_ids:
        try:
            uids.append(uuid.UUID(sid))
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail=f"Invalid application ID format: {sid}")
    
    stmt = select(Application).where(Application.internal_uid.in_(uids))
    result = await session.exec(stmt)
    applications = result.all()
    
    print(f"DEBUG: Found {len(applications)} apps. Requested {len(payment_in.application_ids)}")

    if len(applications) != len(payment_in.application_ids):
        found_uids = {str(app.internal_uid) for app in applications}
        missing = [s for s in payment_in.application_ids if s not in found_uids]
        print(f"DEBUG: Missing IDs: {missing}")
        raise HTTPException(status_code=404, detail=f"One or more applications not found: {missing}")

    for app in applications:
        if app.user_id != current_user.id:
            print(f"DEBUG: Permission denied for App {app.internal_uid}. Owner: {app.user_id}, Requester: {current_user.id}")
            raise HTTPException(status_code=403, detail=f"Permission denied for application {app.internal_uid}")
        
        # Check if payable (Must be Draft or Pending Payment)
        if app.status not in [ApplicationStatus.DRAFT, ApplicationStatus.PENDING_PAYMENT]:
             raise HTTPException(
                status_code=400, 
                detail=f"Application {app.internal_uid} cannot be paid for. Current status: {app.status}"
            )
        
        # Check if already paid (Step 5 = after payment; Step 3 = company info, Step 4 = payment)
        if app.current_step >= 5:
             raise HTTPException(
                status_code=400, 
                detail=f"Application {app.internal_uid} is already paid."
            )
        # Require company info so the invoice can be generated with correct details
        company_check = await session.exec(select(CompanyInfo).where(CompanyInfo.application_id == app.id))
        if not company_check.first():
            raise HTTPException(
                status_code=400,
                detail=f"Complete company information before payment for application {app.internal_uid}.",
            )

        # Update status and step (in memory; commit only after invoices are uploaded)
        app.status = ApplicationStatus.DRAFT
        app.current_step = 5
        session.add(app)
        updated_apps.append(app)

    # Generate invoice PDFs and upload to storage BEFORE committing payment.
    # If this fails we do not commit, so the user can retry.
    generated_invoices: list[tuple[Application, bytes]] = []
    try:
        for app in updated_apps:
            result = await session.exec(
                select(Application).where(Application.id == app.id).options(selectinload(Application.company_info))
            )
            app_with_company = result.one()
            pdf_buffer, invoice_number = invoice_pdf_generator.generate(
                app_with_company, app_with_company.company_info
            )
            pdf_bytes = pdf_buffer.getvalue()
            app_with_company.invoice_number = invoice_number
            session.add(app_with_company)
            filename = _invoice_filename(app_with_company, invoice_number)
            storage_service.upload_invoice(pdf_bytes, app.id, filename)
            generated_invoices.append((app, pdf_bytes))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Invoice generation or upload failed. Ensure Supabase storage is configured (SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_BUCKET_NAME) and the bucket exists. Error: {e!s}",
        )

    await session.commit()

    # Send invoice emails (best-effort; do not fail the request)
    for app, pdf_bytes in generated_invoices:
        if app.user_id:
            user = await session.get(User, app.user_id)
            if user and user.email:
                try:
                    await send_invoice_email(
                        email_to=user.email,
                        applicant_name=user.email.split("@")[0] if user.email else "Applicant",
                        application_id=app.id,
                        pdf_bytes=pdf_bytes,
                    )
                except Exception as e:
                    print(f"Invoice email failed for application {app.internal_uid}: {e}")

    # Load user for response (we did not selectinload User on applications)
    user_map: dict[int, User] = {}
    for app in updated_apps:
        if app.user_id and app.user_id not in user_map:
            u = await session.get(User, app.user_id)
            if u:
                user_map[app.user_id] = u

    return [
        ApplicationRead.from_application(
            app,
            user_email=user_map[app.user_id].email if app.user_id and app.user_id in user_map else None,
        )
        for app in updated_apps
    ]

@router.get("/{application_uid}/details", response_model=ApplicationDetailsResponse)
async def get_application_details(
    application_uid: uuid.UUID,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
):
    """
    Get full details of a specific application for user review before final submission.
    Includes company info, directors, and documents with signed URLs for documents.
    """
    result = await deps.get_application_by_uid(session, application_uid)
    if not result:
        raise HTTPException(status_code=404, detail="Application not found")
    app_result = await session.exec(
        select(Application).where(Application.id == result.id).options(
            selectinload(Application.company_info),
            selectinload(Application.directors),
            selectinload(Application.documents)
        )
    )
    result = app_result.one()
    if result.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    details = ApplicationDetailsResponse(
        id=str(result.internal_uid),
        certificate_type=result.certificate_type,
        certificate_class=result.certificate_class,
        description=result.description,
        status=result.status,
        current_step=result.current_step,
        created_at=result.created_at,
        updated_at=result.updated_at,
        company_info=result.company_info.dict() if result.company_info else None,
        directors=[d.dict() for d in result.directors] if result.directors else [],
        documents=[]
    )
    
    if result.documents:
        for doc in result.documents:
            doc_dict = doc.dict()
            if doc.file_url:
                signed_url = storage_service.get_signed_url(doc.file_url)
                if signed_url:
                    doc_dict["file_url"] = signed_url
            details.documents.append(doc_dict)
    
    return details

@router.post("/{application_uid}/submit", response_model=ApplicationRead)
async def submit_application(
    application_uid: uuid.UUID,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
):
    """
    Final submission of application. Changes status from 'draft' to 'submitted'.
    Files are already stored in Supabase Storage; this finalizes the application.
    Validates completeness before allowing submission.
    """
    application = await deps.get_application_by_uid(session, application_uid)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    if application.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    if application.status != ApplicationStatus.DRAFT:
        raise HTTPException(
            status_code=400,
            detail=f"Application is already {application.status}. Only draft applications can be submitted."
        )
    
    company_info_result = await session.exec(select(CompanyInfo).where(CompanyInfo.application_id == application.id))
    if not company_info_result.first():
        raise HTTPException(status_code=400, detail="Cannot submit: Company Information is missing.")
    
    directors_result = await session.exec(select(Director).where(Director.application_id == application.id))
    if not directors_result.first():
        raise HTTPException(status_code=400, detail="Cannot submit: Directors Information is missing.")
    
    documents_result = await session.exec(select(Document).where(Document.application_id == application.id))
    if not documents_result.first():
        raise HTTPException(status_code=400, detail="Cannot submit: Supporting Documents are missing.")
    
    application.status = ApplicationStatus.SUBMITTED
    application.current_step = 7
    session.add(application)
    await session.commit()
    await session.refresh(application)
    
    await notify_admins(
        session=session,
        title="New Application Submitted",
        message=f"Application {application.internal_uid} ({application.certificate_type}) has been submitted for review.",
        link=f"/admin/applications/{application.internal_uid}"
    )
    
    return ApplicationRead.from_application(application, user_email=current_user.email)

@router.get("/{application_uid}", response_model=ApplicationRead)
async def read_application(
    *,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
    application_uid: uuid.UUID,
):
    """
    Get application by UUID (internal_uid).
    """
    application = await deps.get_application_by_uid(session, application_uid)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    if not current_user.is_superuser and (application.user_id != current_user.id):
        raise HTTPException(status_code=400, detail="Not enough permissions")
    return ApplicationRead.from_application(application, user_email=current_user.email)

@router.patch("/{application_uid}", response_model=ApplicationRead)
async def update_application(
    *,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
    application_uid: uuid.UUID,
    application_in: ApplicationUpdate,
):
    """
    Update an application.
    """
    application = await deps.get_application_by_uid(session, application_uid)
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
        company_info_result = await session.exec(select(CompanyInfo).where(CompanyInfo.application_id == application.id))
        if not company_info_result.first():
             raise HTTPException(status_code=400, detail="Cannot submit: Company Information is missing.")
             
        # Check Directors
        directors_result = await session.exec(select(Director).where(Director.application_id == application.id))
        if not directors_result.first():
             raise HTTPException(status_code=400, detail="Cannot submit: Directors Information is missing.")
             
        # Check Documents
        documents_result = await session.exec(select(Document).where(Document.application_id == application.id))
        if not documents_result.first():
             raise HTTPException(status_code=400, detail="Cannot submit: Supporting Documents are missing.")

        # Notify Admins (notify_admins NO LONGER commits)
        await notify_admins(
            session, 
            "New Application Submitted", 
            f"Application {application.internal_uid} has been submitted by {current_user.email}.", 
            link=f"/admin/applications/{application.internal_uid}"
        )

    await session.commit()
    await session.refresh(application)
    return ApplicationRead.from_application(application, user_email=current_user.email)

@router.post("/{application_uid}/renew", response_model=ApplicationRead)
async def renew_application(
    *,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
    application_uid: uuid.UUID,
):
    """
    Renew an existing approved application.
    Creates a new DRAFT application with cloned data (Company Info, Directors).
    """
    original_app = await deps.get_application_by_uid(session, application_uid)
    if not original_app:
        raise HTTPException(status_code=404, detail="Application not found")
    query = select(Application).where(Application.id == original_app.id).options(
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
        c = original_app.company_info
        new_company_info = CompanyInfo(
            company_name=c.company_name,
            registration_number=c.registration_number,
            address=c.address,
            city=c.city,
            country=c.country,
            phone_number=c.phone_number,
            email=c.email,
            application_id=new_app.id,
        )
        session.add(new_company_info)

    for director in original_app.directors:
        new_director = Director(
            name=director.name,
            position=director.position,
            nationality=director.nationality,
            phone_number=getattr(director, "phone_number", None),
            email=getattr(director, "email", None),
            application_id=new_app.id,
        )
        session.add(new_director)

    await session.commit()
    await session.refresh(new_app)
    return ApplicationRead.from_application(new_app, user_email=current_user.email)


@router.get("/renewal-token")
async def get_renewal_token(
    application_uid: uuid.UUID,
    session: AsyncSession = Depends(deps.get_session),
):
    """
    Get a short-lived renewal token for an application (e.g. for use in certificate PDF link).
    Public: no auth required. Only issued for approved applications.
    """
    application = await deps.get_application_by_uid(session, application_uid)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    if application.status != ApplicationStatus.APPROVED:
        raise HTTPException(status_code=400, detail="Only approved certificates can be renewed.")
    token = create_renewal_token(str(application.internal_uid))
    return {"token": token}


@router.post("/renew-from-token", response_model=ApplicationRead)
async def renew_from_token(
    body: RenewFromTokenRequest,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
):
    """
    Start a renewal using a token from the certificate renewal link.
    Requires authentication; token is consumed to identify the application.
    """
    application_uid_str = decode_renewal_token(body.token)
    if application_uid_str is None:
        raise HTTPException(status_code=400, detail="Invalid or expired renewal token.")
    try:
        application_uid = uuid.UUID(application_uid_str)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid or expired renewal token.")
    original_app = await deps.get_application_by_uid(session, application_uid)
    if not original_app:
        raise HTTPException(status_code=404, detail="Application not found")
    result = await session.exec(
        select(Application).where(Application.id == original_app.id).options(
            selectinload(Application.company_info),
            selectinload(Application.directors),
        )
    )
    original_app = result.one()
    if original_app.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    if original_app.status != ApplicationStatus.APPROVED:
        raise HTTPException(status_code=400, detail="Only approved applications can be renewed.")
    new_app = Application(
        certificate_type=original_app.certificate_type,
        certificate_class=original_app.certificate_class,
        description=f"Renewal of Application #{original_app.id}",
        status=ApplicationStatus.DRAFT,
        current_step=4,
        user_id=current_user.id,
    )
    session.add(new_app)
    await session.commit()
    if original_app.company_info:
        c = original_app.company_info
        new_company_info = CompanyInfo(
            company_name=c.company_name,
            registration_number=c.registration_number,
            address=c.address,
            city=c.city,
            country=c.country,
            phone_number=c.phone_number,
            email=c.email,
            application_id=new_app.id,
        )
        session.add(new_company_info)
    for director in original_app.directors:
        new_director = Director(
            name=director.name,
            position=director.position,
            nationality=director.nationality,
            phone_number=getattr(director, "phone_number", None),
            email=getattr(director, "email", None),
            application_id=new_app.id,
        )
        session.add(new_director)
    await session.commit()
    await session.refresh(new_app)
    return ApplicationRead.from_application(new_app, user_email=current_user.email)


@router.post("/{application_uid}/cancel", response_model=ApplicationRead)
async def cancel_application(
    *,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
    application_uid: uuid.UUID,
):
    """
    Cancel an application.
    Only allows cancellation if status is DRAFT, PENDING_PAYMENT, or SUBMITTED.
    """
    application = await deps.get_application_by_uid(session, application_uid)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    if application.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

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
    return ApplicationRead.from_application(application, user_email=current_user.email)