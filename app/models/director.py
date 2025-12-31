from typing import Optional
from sqlmodel import Field, Relationship, SQLModel

class DirectorBase(SQLModel):
    name: str
    position: str # e.g., CEO, Managing Director
    nationality: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None

class Director(DirectorBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Foreign key to Application (One Application -> Many Directors)
    application_id: int = Field(foreign_key="application.id")
    application: "Application" = Relationship(back_populates="directors")

class DirectorCreate(DirectorBase):
    application_id: int

class DirectorRead(DirectorBase):
    id: int
    application_id: int

class DirectorUpdate(SQLModel):
    name: Optional[str] = None
    position: Optional[str] = None
    nationality: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
