from typing import Optional
from sqlmodel import Field, Relationship, SQLModel

class CompanyInfoBase(SQLModel):
    company_name: str
    registration_number: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None # Company email, might differ from user's email

class CompanyInfo(CompanyInfoBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Foreign key to Application
    application_id: int = Field(foreign_key="application.id", unique=True)
    application: "Application" = Relationship(back_populates="company_info")

class CompanyInfoCreate(CompanyInfoBase):
    application_id: int

class CompanyInfoRead(CompanyInfoBase):
    id: int
    application_id: int

class CompanyInfoUpdate(SQLModel):
    company_name: Optional[str] = None
    registration_number: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
