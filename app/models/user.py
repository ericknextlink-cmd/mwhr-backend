from typing import List, Optional, TYPE_CHECKING
from enum import Enum
import uuid
from sqlmodel import Field, Relationship, SQLModel, Column, String
from sqlalchemy import types

if TYPE_CHECKING:
    from app.models.application import Application

class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin" # Staff
    SUPER_ADMIN = "super_admin" # Ministry Official

class CompanyType(str, Enum):
    SOLE_PROPRIETORSHIP = "Sole Proprietorship"
    LIMITED_LIABILITY = "Limited Liability"
    PARTNERSHIP = "Partnership"
    EXTERNAL_COMPANY = "External Company"
    OTHER = "Other"

class UserBase(SQLModel):
    email: str = Field(unique=True, index=True)
    full_name: Optional[str] = Field(default=None)
    phone_number: Optional[str] = Field(default=None)
    
    # New Fields for Company Registration
    company_registration_number: Optional[str] = Field(default=None, index=True, unique=True)
    company_type: Optional[str] = Field(default=None) # Storing as string to allow flexibility, or use Enum
    
    is_active: bool = Field(default=True)
    is_verified: bool = Field(default=False)
    is_superuser: bool = Field(default=False) # Keep for backward compatibility for now, sync with role later
    role: UserRole = Field(default=UserRole.USER, sa_column=Column(String))
    tutorials_completed: bool = Field(default=False)

class User(UserBase, table=True):
    id: Optional[uuid.UUID] = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(types.UUID, primary_key=True, default=uuid.uuid4)
    )
    hashed_password: str
    
    applications: List["Application"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"foreign_keys": "[Application.user_id]"}
    )
    
    assigned_applications: List["Application"] = Relationship(
        back_populates="reviewer",
        sa_relationship_kwargs={"foreign_keys": "[Application.assigned_to]"}
    )

class UserCreate(UserBase):
    password: str

class UserRead(UserBase):
    id: uuid.UUID
    role: UserRole

class UserUpdate(SQLModel):
    email: Optional[str] = None
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None
    role: Optional[UserRole] = None
    tutorials_completed: Optional[bool] = None