from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api import deps
from app.models.user import User, UserRead, UserUpdate, UserRole, UserCreate
from app.models.audit_log import AuditLog, AuditLogRead
from app.core.security import get_password_hash
from app.services.audit_service import log_audit_event

router = APIRouter()

@router.get("/users", response_model=List[UserRead])
async def read_users(
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_superuser),
):
    """
    Retrieve all users. Accessible only by superusers.
    """
    users = await session.exec(select(User))
    return users.all()

@router.patch("/users/{user_id}/role", response_model=UserRead)
async def update_user_role(
    *,
    session: AsyncSession = Depends(deps.get_session),
    user_id: int,
    new_role: UserRole,
    current_user: User = Depends(deps.get_current_active_superuser),
):
    """
    Update a user's role. Accessible only by superusers.
    """
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Prevent superuser from demoting themselves or changing another superuser's role without care (optional)
    if user.id == current_user.id and new_role != current_user.role:
        raise HTTPException(status_code=403, detail="Cannot change your own role this way.")
    
    user.role = new_role
    
    # Sync is_superuser flag with role
    if new_role == UserRole.SUPER_ADMIN:
        user.is_superuser = True
    elif new_role == UserRole.ADMIN:
        user.is_superuser = True # Admins also have superuser flag to keep existing permissions structure
    else: # UserRole.USER
        user.is_superuser = False

    session.add(user)
    
    role_str = new_role.value.replace("_", " ").title()
    await log_audit_event(
        session,
        user_id=current_user.id,
        action="USER_ROLE_UPDATED",
        target_type="user",
        target_id=user.id,
        target_label=user.email,
        details=f"Role changed to {role_str}"
    )

    await session.commit()
    await session.refresh(user)
    return user

@router.patch("/users/{user_id}/activate", response_model=UserRead)
async def toggle_user_active_status(
    *,
    session: AsyncSession = Depends(deps.get_session),
    user_id: int,
    activate: bool,
    current_user: User = Depends(deps.get_current_active_superuser),
):
    """
    Activate or deactivate a user. Accessible only by superusers.
    """
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user.id == current_user.id:
        raise HTTPException(status_code=403, detail="Cannot deactivate your own account.")

    user.is_active = activate
    session.add(user)
    
    await log_audit_event(
        session,
        user_id=current_user.id,
        action="USER_STATUS_UPDATED",
        target_type="user",
        target_id=user.id,
        target_label=user.email,
        details=f"Active status changed to {activate}"
    )

    await session.commit()
    await session.refresh(user)
    return user

@router.post("/users", response_model=UserRead)
async def create_user(
    *,
    session: AsyncSession = Depends(deps.get_session),
    user_in: UserCreate,
    role: UserRole = UserRole.USER, # Default to USER if not specified, but UI will likely specify
    current_user: User = Depends(deps.get_current_active_superuser),
):
    """
    Create a new user. Accessible only by superusers.
    """
    user = await session.exec(select(User).where(User.email == user_in.email))
    if user.first():
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system",
        )
    
    # Create user manually to handle password hashing
    user = User(
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
        is_active=user_in.is_active,
        is_superuser=user_in.is_superuser,
        role=role
    )
    
    session.add(user)
    await session.commit()
    await session.refresh(user)

    role_str = role.value.replace("_", " ").title()
    await log_audit_event(
        session,
        user_id=current_user.id,
        action="USER_CREATED",
        target_type="user",
        target_id=user.id,
        target_label=user.email,
        details=f"Created user {user.email} with role {role_str}"
    )
    await session.commit()

    return user

from datetime import datetime

@router.get("/audit-logs", response_model=List[AuditLogRead])
async def read_audit_logs(
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_superuser),
    skip: int = 0,
    limit: int = 100,
    action: Optional[str] = None,
    user_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
):
    """
    Retrieve audit logs. Accessible only by superusers.
    """
    # Fetch logs with user details
    from sqlalchemy.orm import selectinload
    query = select(AuditLog).options(selectinload(AuditLog.user))
    
    if action:
        query = query.where(AuditLog.action == action)
    if user_id:
        query = query.where(AuditLog.user_id == user_id)
    if start_date:
        query = query.where(AuditLog.timestamp >= start_date)
    if end_date:
        query = query.where(AuditLog.timestamp <= end_date)
        
    query = query.order_by(AuditLog.timestamp.desc()).offset(skip).limit(limit)
    result = await session.exec(query)
    logs = result.all()
    
    # Map to Read model (including user_email)
    read_logs = []
    for log in logs:
        read_logs.append(AuditLogRead(
            id=log.id,
            action=log.action,
            target_type=log.target_type,
            target_id=log.target_id,
            target_label=log.target_label, # Add label
            details=log.details,
            timestamp=log.timestamp,
            user_id=log.user_id,
            user_email=log.user.email if log.user else "Unknown"
        ))
        
    return read_logs

