from typing import Optional
from datetime import datetime
from sqlmodel import Field, Relationship, SQLModel

class AuditLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    action: str
    target_type: str # "application", "user", etc.
    target_id: int
    target_label: Optional[str] = None # E.g. "user@email.com" or "Application #123"
    details: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Who performed the action
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    user: Optional["User"] = Relationship()

class AuditLogRead(SQLModel):
    id: int
    action: str
    target_type: str
    target_id: int
    target_label: Optional[str] = None
    details: Optional[str]
    timestamp: datetime
    user_id: int
    user_email: Optional[str] = None # Computed field
