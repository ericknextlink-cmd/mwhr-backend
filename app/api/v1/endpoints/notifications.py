from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select, col
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api import deps
from app.models.notification import Notification, NotificationRead, NotificationUpdate
from app.models.user import User

router = APIRouter()

@router.get("/", response_model=List[NotificationRead])
async def read_notifications(
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_user),
    skip: int = 0,
    limit: int = 50,
    unread_only: bool = False
):
    """
    Get notifications for the current user.
    """
    query = select(Notification).where(Notification.user_id == current_user.id)
    
    if unread_only:
        query = query.where(Notification.is_read == False)
        
    query = query.order_by(col(Notification.created_at).desc()).offset(skip).limit(limit)
    
    notifications = await session.exec(query)
    return notifications.all()

@router.patch("/{id}/read", response_model=NotificationRead)
async def mark_notification_read(
    id: int,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Mark a notification as read.
    """
    notification = await session.get(Notification, id)
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    if notification.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
        
    notification.is_read = True
    session.add(notification)
    await session.commit()
    await session.refresh(notification)
    return notification
