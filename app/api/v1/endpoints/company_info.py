import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api import deps
from app.models.application import Application
from app.models.company_info import CompanyInfo, CompanyInfoCreate, CompanyInfoRead, CompanyInfoUpdate
from app.models.user import User

router = APIRouter()

@router.post("/", response_model=CompanyInfoRead)
async def create_company_info(
    *,
    session: AsyncSession = Depends(deps.get_session),
    company_info_in: CompanyInfoCreate,
    current_user: User = Depends(deps.get_current_user),
):
    """
    Create company information for a specific application.
    An application can only have one company_info. application_id is the application UUID (internal_uid).
    """
    try:
        app_uid = uuid.UUID(company_info_in.application_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid application ID format")
    application = await deps.get_application_by_uid(session, app_uid)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    if application.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    existing_company_info = await session.exec(
        select(CompanyInfo).where(CompanyInfo.application_id == application.id)
    )
    if existing_company_info.first():
        raise HTTPException(status_code=400, detail="Company information already exists for this application.")

    data = company_info_in.model_dump(exclude={"application_id"})
    # Seed from registration: if any field is missing/empty, use current user's registration data
    if not (data.get("company_name") or "").strip() and current_user.full_name:
        data["company_name"] = current_user.full_name.strip()
    if not (data.get("registration_number") or "").strip() and current_user.company_registration_number:
        data["registration_number"] = current_user.company_registration_number.strip()
    if not (data.get("phone_number") or "").strip() and current_user.phone_number:
        data["phone_number"] = current_user.phone_number.strip()
    if not (data.get("email") or "").strip() and current_user.email:
        data["email"] = current_user.email.strip()
    company_info = CompanyInfo(**data, application_id=application.id)
    session.add(company_info)
    # Next step is Payment (company info before payment)
    if application.current_step < 4:
        application.current_step = 4
        session.add(application)
    await session.commit()
    await session.refresh(company_info)
    return company_info

@router.get("/latest/data", response_model=CompanyInfoRead)
async def read_latest_company_info(
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
):
    """
    Get the company info from the user's most recent application.
    """
    # 1. Find user's applications, order by created_at DESC
    app_query = select(Application).where(Application.user_id == current_user.id).order_by(Application.created_at.desc())
    apps = await session.exec(app_query)
    all_apps = apps.all()
    
    # 2. Iterate to find first one with company info
    for app in all_apps:
        # Check if company info exists
        info_query = select(CompanyInfo).where(CompanyInfo.application_id == app.id)
        info_result = await session.exec(info_query)
        info = info_result.first()
        if info:
            return info
            
    raise HTTPException(status_code=404, detail="No previous company info found")

@router.get("/{application_uid}", response_model=CompanyInfoRead)
async def read_company_info(
    *,
    session: AsyncSession = Depends(deps.get_session),
    application_uid: uuid.UUID,
    current_user: User = Depends(deps.get_current_user),
):
    """
    Retrieve company information for a specific application. application_uid is the application UUID (internal_uid).
    """
    application = await deps.get_application_by_uid(session, application_uid)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    if application.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    company_info = await session.exec(
        select(CompanyInfo).where(CompanyInfo.application_id == application.id)
    )
    result = company_info.first()
    if not result:
        raise HTTPException(status_code=404, detail="Company information not found for this application.")
    return result

@router.patch("/{application_uid}", response_model=CompanyInfoRead)
async def update_company_info(
    *,
    session: AsyncSession = Depends(deps.get_session),
    application_uid: uuid.UUID,
    company_info_in: CompanyInfoUpdate,
    current_user: User = Depends(deps.get_current_user),
):
    """
    Update company information for a specific application.
    """
    application = await deps.get_application_by_uid(session, application_uid)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    if application.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    company_info = await session.exec(
        select(CompanyInfo).where(CompanyInfo.application_id == application.id)
    )
    db_company_info = company_info.first()
    if not db_company_info:
        raise HTTPException(status_code=404, detail="Company information not found for this application.")
    
    company_info_data = company_info_in.model_dump(exclude_unset=True)
    for key, value in company_info_data.items():
        setattr(db_company_info, key, value)
    
    session.add(db_company_info)
    
    if application.current_step < 4:
        application.current_step = 4
        session.add(application)

    await session.commit()
    await session.refresh(db_company_info)
    return db_company_info
