from typing import Optional, TYPE_CHECKING, List, Any, Dict
from enum import Enum
from datetime import datetime
import uuid
from sqlmodel import Field, Relationship, SQLModel, Column
from sqlalchemy.types import JSON

if TYPE_CHECKING:
    from app.models.company_info import CompanyInfo
    from app.models.director import Director
    from app.models.document import Document

class ApplicationStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    PENDING_PAYMENT = "pending_payment"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    SUSPENDED = "suspended"

class CertificateType(str, Enum):
    ELECTRICAL = "electrical"
    BUILDING = "building"
    PLUMBING = "plumbing"
    CIVIL = "civil"


# Highest class per type (upgrade logic: user cannot start new app for this type if already at highest)
HIGHEST_CLASS_BY_TYPE: Dict[CertificateType, str] = {
    CertificateType.ELECTRICAL: "E1",
    CertificateType.BUILDING: "D1K1",
    CertificateType.CIVIL: "D1K1",
    CertificateType.PLUMBING: "G1",
}


class ApplicationBase(SQLModel):
    certificate_type: CertificateType
    certificate_class: Optional[str] = None # A, B, C, etc.
    description: Optional[str] = None
    status: ApplicationStatus = Field(default=ApplicationStatus.DRAFT)
    current_step: int = Field(default=1) # 1: Apply, 2: Select Class, etc.
    expiry_date: Optional[datetime] = Field(default=None) # Expiry date for approved certificates
    issued_date: Optional[datetime] = Field(default=None) # Date the certificate was first approved

class Application(ApplicationBase, table=True):
    """
    DB table: id is integer PK (int4) by design. Do not change to UUID.
    Public identifier for APIs and frontend is internal_uid (UUID); ApplicationRead.id exposes that.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Security Fields (XSCNS)
    certificate_number: Optional[str] = Field(default=None, index=True, unique=True)
    internal_uid: uuid.UUID = Field(default_factory=uuid.uuid4, index=True, unique=True, nullable=False)
    security_token: Optional[str] = Field(default=None, index=True)
    certificate_pdf_hash: Optional[str] = Field(default=None, index=True) # SHA-256 hash for tamper detection
    certificate_open_password_hash: Optional[str] = Field(default=None) # Argon2 hash of password to open PDF; we never have access to Supabase user password hash

    # Foreign Key to User (Applicant)
    user_id: Optional[uuid.UUID] = Field(default=None, foreign_key="user.id")
    user: Optional["User"] = Relationship(
        back_populates="applications",
        sa_relationship_kwargs={"foreign_keys": "[Application.user_id]"}
    )
    
    # Reviewer Assignment
    assigned_to: Optional[uuid.UUID] = Field(default=None, foreign_key="user.id")
    reviewer: Optional["User"] = Relationship(
        back_populates="assigned_applications",
        sa_relationship_kwargs={"foreign_keys": "[Application.assigned_to]"}
    )
    
    company_info: Optional["CompanyInfo"] = Relationship(back_populates="application")
    
    directors: List["Director"] = Relationship(back_populates="application")
    
    documents: List["Document"] = Relationship(back_populates="application")

    # Stored AI analysis result (avoids re-running analysis; one canonical result per application)
    ai_analysis_json: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON, nullable=True))

    # Invoice number from first generation (e.g. INV-2026-000214) for friendly filename and storage path
    invoice_number: Optional[str] = Field(default=None, nullable=True)

class ApplicationCreate(ApplicationBase):
    pass

class ApplicationRead(ApplicationBase):
    """id is the application's public UUID (internal_uid), not the internal integer PK."""
    id: str  # UUID string (internal_uid)
    created_at: datetime
    updated_at: datetime
    user_id: uuid.UUID
    expiry_date: Optional[datetime] = None
    issued_date: Optional[datetime] = None
    certificate_number: Optional[str] = None
    assigned_to: Optional[uuid.UUID] = None
    company_name: Optional[str] = None
    user_email: Optional[str] = None

    @classmethod
    def from_application(
        cls,
        app: "Application",
        company_name: Optional[str] = None,
        user_email: Optional[str] = None,
        include_assigned_to: bool = True,
    ) -> "ApplicationRead":
        """Build ApplicationRead from Application; id is the UUID (internal_uid). Set include_assigned_to=False for applicants."""
        return cls(
            id=str(app.internal_uid),
            certificate_type=app.certificate_type,
            certificate_class=app.certificate_class,
            description=app.description,
            status=app.status,
            current_step=app.current_step,
            created_at=app.created_at,
            updated_at=app.updated_at,
            user_id=app.user_id,
            expiry_date=app.expiry_date,
            issued_date=app.issued_date,
            certificate_number=app.certificate_number,
            assigned_to=app.assigned_to if include_assigned_to else None,
            company_name=company_name,
            user_email=user_email,
        )


class ApplicationReadForApplicant(ApplicationBase):
    """Same as ApplicationRead but without assigned_to (applicants must not see reviewer assignment)."""
    id: str
    created_at: datetime
    updated_at: datetime
    user_id: uuid.UUID
    expiry_date: Optional[datetime] = None
    issued_date: Optional[datetime] = None
    certificate_number: Optional[str] = None
    company_name: Optional[str] = None
    user_email: Optional[str] = None

    @classmethod
    def from_application(
        cls,
        app: "Application",
        company_name: Optional[str] = None,
        user_email: Optional[str] = None,
    ) -> "ApplicationReadForApplicant":
        return cls(
            id=str(app.internal_uid),
            certificate_type=app.certificate_type,
            certificate_class=app.certificate_class,
            description=app.description,
            status=app.status,
            current_step=app.current_step,
            created_at=app.created_at,
            updated_at=app.updated_at,
            user_id=app.user_id,
            expiry_date=app.expiry_date,
            issued_date=app.issued_date,
            certificate_number=app.certificate_number,
            company_name=company_name,
            user_email=user_email,
        )


class ApplicationUpdate(SQLModel):
    certificate_type: Optional[CertificateType] = None
    certificate_class: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None # Use str to avoid Pydantic enum validation issues
    current_step: Optional[int] = None

class ApplicationReadAdmin(ApplicationRead):
    """Admin list response: includes integer DB id for display (id column = init id)."""
    company_name: Optional[str] = None
    user_email: Optional[str] = None
    internal_id: Optional[int] = None  # DB PK; show in admin ID column

