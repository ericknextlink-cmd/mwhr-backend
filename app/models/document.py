from typing import Optional
from enum import Enum
from datetime import datetime
from sqlmodel import Field, Relationship, SQLModel

class DocumentType(str, Enum):
    INCORPORATION_CERT = "incorporation_cert"
    COMMENCEMENT_CERT = "commencement_cert"
    TAX_CLEARANCE = "tax_clearance"
    SSNIT_CLEARANCE = "ssnit_clearance"
    OTHER = "other"

class DocumentBase(SQLModel):
    document_type: DocumentType
    filename: str
    file_url: str # Path to file on disk or S3 URL

class Document(DocumentBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    
    application_id: int = Field(foreign_key="application.id")
    application: "Application" = Relationship(back_populates="documents")

class DocumentCreate(DocumentBase):
    application_id: int

class DocumentRead(DocumentBase):
    id: int
    uploaded_at: datetime
    application_id: int
