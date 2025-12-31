from typing import List, Optional, TYPE_CHECKING
from enum import Enum
from sqlmodel import Field, Relationship, SQLModel, Column, String

if TYPE_CHECKING:
    from app.models.application import Application

class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin" # Staff
    SUPER_ADMIN = "super_admin" # Ministry Official

class UserBase(SQLModel):
    email: str = Field(unique=True, index=True)
    full_name: Optional[str] = Field(default=None)
    phone_number: Optional[str] = Field(default=None)
    is_active: bool = Field(default=True)
    is_superuser: bool = Field(default=False) # Keep for backward compatibility for now, sync with role later
    role: UserRole = Field(default=UserRole.USER, sa_column=Column(String))

class User(UserBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
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
    id: int
    role: UserRole

class UserUpdate(SQLModel):
    email: Optional[str] = None
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None
    role: Optional[UserRole] = None
