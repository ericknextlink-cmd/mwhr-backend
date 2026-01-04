from typing import Optional, TYPE_CHECKING, List
from enum import Enum
from datetime import datetime
import uuid
from sqlmodel import Field, Relationship, SQLModel

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

class ApplicationBase(SQLModel):
    certificate_type: CertificateType
    certificate_class: Optional[str] = None # A, B, C, etc.
    description: Optional[str] = None
    status: ApplicationStatus = Field(default=ApplicationStatus.DRAFT)
    current_step: int = Field(default=1) # 1: Apply, 2: Select Class, etc.
    expiry_date: Optional[datetime] = Field(default=None) # Expiry date for approved certificates
    issued_date: Optional[datetime] = Field(default=None) # Date the certificate was first approved

class Application(ApplicationBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Security Fields (XSCNS)
    certificate_number: Optional[str] = Field(default=None, index=True, unique=True)
    internal_uid: uuid.UUID = Field(default_factory=uuid.uuid4, index=True, unique=True, nullable=False)
    security_token: Optional[str] = Field(default=None, index=True)

    # Foreign Key to User (Applicant)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    user: Optional["User"] = Relationship(
        back_populates="applications",
        sa_relationship_kwargs={"foreign_keys": "[Application.user_id]"}
    )
    
    # Reviewer Assignment
    assigned_to: Optional[int] = Field(default=None, foreign_key="user.id")
    reviewer: Optional["User"] = Relationship(
        back_populates="assigned_applications",
        sa_relationship_kwargs={"foreign_keys": "[Application.assigned_to]"}
    )
    
    company_info: Optional["CompanyInfo"] = Relationship(back_populates="application")
    
    directors: List["Director"] = Relationship(back_populates="application")
    
    documents: List["Document"] = Relationship(back_populates="application")

class ApplicationCreate(ApplicationBase):
    pass

class ApplicationRead(ApplicationBase):
    id: int
    created_at: datetime
    updated_at: datetime
    user_id: int
    expiry_date: Optional[datetime] = None
    issued_date: Optional[datetime] = None
    certificate_number: Optional[str] = None
    assigned_to: Optional[int] = None
    company_name: Optional[str] = None
    user_email: Optional[str] = None

class ApplicationUpdate(SQLModel):
    certificate_type: Optional[CertificateType] = None
    certificate_class: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None # Use str to avoid Pydantic enum validation issues
    current_step: Optional[int] = None

class ApplicationReadAdmin(ApplicationRead):
    company_name: Optional[str] = None
    user_email: Optional[str] = None

