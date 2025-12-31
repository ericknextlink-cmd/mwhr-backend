from typing import Optional
from datetime import datetime
from sqlmodel import Field, Relationship, SQLModel

class NotificationBase(SQLModel):
    user_id: int # The admin receiving this notification
    title: str
    message: str
    is_read: bool = Field(default=False)
    link: Optional[str] = None # Optional link to the application (e.g. /admin/applications/5)

class Notification(NotificationBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Foreign key to User
    # user_id is defined in Base

class NotificationCreate(NotificationBase):
    pass

class NotificationRead(NotificationBase):
    id: int
    created_at: datetime

class NotificationUpdate(SQLModel):
    is_read: Optional[bool] = None
