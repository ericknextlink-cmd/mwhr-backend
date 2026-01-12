from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from app.db.session import get_session
from app.models.user import User, UserCreate, UserRead
from app.core.security import get_password_hash, verify_password, create_verification_token, verify_token
from app.api import deps
from app.services import email_service
from pydantic import BaseModel

router = APIRouter()

@router.post("/verify-email/{token}", response_model=dict)
async def verify_email(
    token: str,
    session: AsyncSession = Depends(deps.get_session),
):
    """
    Verify email with token.
    """
    email = verify_token(token)
    if not email:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    
    statement = select(User).where(User.email == email)
    result = await session.exec(statement)
    user = result.first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.is_verified = True
    session.add(user)
    await session.commit()
    
    return {"message": "Email verified successfully"}

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class UserProfileUpdate(BaseModel):
    full_name: str | None = None
    phone_number: str | None = None

@router.get("/me", response_model=UserRead)
async def read_user_me(
    current_user: User = Depends(deps.get_current_user),
):
    """
    Get current user.
    """
    return current_user

@router.patch("/me", response_model=UserRead)
async def update_user_me(
    *,
    session: AsyncSession = Depends(deps.get_session),
    profile_in: UserProfileUpdate,
    current_user: User = Depends(deps.get_current_user),
):
    """
    Update own profile information.
    """
    if profile_in.full_name is not None:
        current_user.full_name = profile_in.full_name
    if profile_in.phone_number is not None:
        current_user.phone_number = profile_in.phone_number
        
    session.add(current_user)
    await session.commit()
    await session.refresh(current_user)
    return current_user

@router.put("/me/password", response_model=dict)
async def update_password(
    *,
    session: AsyncSession = Depends(deps.get_session),
    password_in: PasswordChange,
    current_user: User = Depends(deps.get_current_user),
):
    """
    Update current user's password.
    """
    if not verify_password(password_in.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect current password")
    
    current_user.hashed_password = get_password_hash(password_in.new_password)
    session.add(current_user)
    await session.commit()
    
    return {"message": "Password updated successfully"}

@router.post("/", response_model=UserRead)
async def create_user(*, session: AsyncSession = Depends(get_session), user_in: UserCreate):
    # Normalize email
    user_in.email = user_in.email.lower()
    
    # Check if user with email already exists
    statement = select(User).where(User.email == user_in.email)
    result = await session.exec(statement)
    user = result.first()
    
    if user:
        raise HTTPException(status_code=400, detail="User with this email already exists")
    
    # Check if user with company registration number already exists (if provided)
    if user_in.company_registration_number:
        statement_reg = select(User).where(User.company_registration_number == user_in.company_registration_number)
        result_reg = await session.exec(statement_reg)
        existing_reg = result_reg.first()
        if existing_reg:
            raise HTTPException(status_code=400, detail="A user with this Company Registration Number already exists.")

    hashed_password = get_password_hash(user_in.password)
    user = User(
        email=user_in.email, 
        hashed_password=hashed_password,
        full_name=user_in.full_name, # Map companyName to full_name if needed, or stick to explicit fields
        phone_number=user_in.phone_number,
        company_registration_number=user_in.company_registration_number,
        company_type=user_in.company_type,
        is_active=True, # Default to active
        is_verified=False, # Must verify email
        is_superuser=False # Default to not superuser
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    # Send verification email
    verification_token = create_verification_token(user.email)
    await email_service.send_verification_email(user.email, verification_token)

    return user

@router.get("/", response_model=List[UserRead])
async def read_users(
    session: AsyncSession = Depends(get_session), skip: int = 0, limit: int = 100
):
    users = await session.exec(User).offset(skip).limit(limit).all()
    return users
