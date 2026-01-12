from datetime import timedelta
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status, Body
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from app.api import deps
from app.core import security
from app.core.config import settings
from app.models.token import Token
from app.models.user import User
from app.services import email_service

router = APIRouter()

@router.post("/login/password-recovery/{email}", response_model=Any)
async def recover_password(
    email: str,
    session: AsyncSession = Depends(deps.get_session),
) -> Any:
    """
    Password Recovery
    """
    # Normalize email to lowercase
    email = email.lower()
    
    result = await session.exec(select(User).where(User.email == email))
    user = result.first()

    if not user:
        # We generally return success even if user not found to prevent email enumeration
        # But for this internal app, maybe clear feedback is better?
        # Let's stick to best practice: Return success but don't send email.
        # OR: Return 404 if we don't care about enumeration (common in enterprise apps).
        # Let's return 404 for clarity in this specific project context.
        raise HTTPException(
            status_code=404,
            detail="The user with this email does not exist in the system.",
        )
    
    password_reset_token = security.create_password_reset_token(email=email)
    await email_service.send_reset_password_email(
        email_to=user.email, email=email, token=password_reset_token
    )
    return {"msg": "Password recovery email sent"}


@router.post("/login/reset-password", response_model=Any)
async def reset_password(
    token: str = Body(...),
    new_password: str = Body(...),
    session: AsyncSession = Depends(deps.get_session),
) -> Any:
    """
    Reset password
    """
    email = security.verify_token(token)
    if not email:
        raise HTTPException(status_code=400, detail="Invalid token")
    
    result = await session.exec(select(User).where(User.email == email))
    user = result.first()
    
    if not user:
        raise HTTPException(status_code=404, detail="The user does not exist in the system.")
    
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
        
    user.hashed_password = security.get_password_hash(new_password)
    session.add(user)
    await session.commit()
    
    return {"msg": "Password updated successfully"}


@router.post("/login/access-token", response_model=Token)
async def login_access_token(
    session: AsyncSession = Depends(deps.get_session),
    form_data: OAuth2PasswordRequestForm = Depends()
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    # Find user by email (using username field from form)
    # Normalize email to lowercase
    email = form_data.username.lower()
    
    statement = select(User).where(User.email == email)
    result = await session.exec(statement)
    user = result.first()

    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect email or password"
        )
        
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
        
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email not verified. Please check your inbox for the verification link."
        )
        
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return {
        "access_token": security.create_access_token(
            user.id, expires_delta=access_token_expires
        ),
        "token_type": "bearer",
    }
