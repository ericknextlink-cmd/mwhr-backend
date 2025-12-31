from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api import deps
from app.models.application import Application
from app.models.company_info import CompanyInfo, CompanyInfoCreate, CompanyInfoRead, CompanyInfoUpdate
from app.models.user import User

router = APIRouter()

async def verify_application_ownership(
    session: AsyncSession, application_id: int, user_id: int
) -> Application:
    """Helper to verify if an application belongs to a user."""
    application = await session.get(Application, application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    if application.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return application

@router.post("/", response_model=CompanyInfoRead)
async def create_company_info(
    *,
    session: AsyncSession = Depends(deps.get_session),
    company_info_in: CompanyInfoCreate,
    current_user: User = Depends(deps.get_current_user),
):
    """
    Create company information for a specific application.
    An application can only have one company_info.
    """
    await verify_application_ownership(session, company_info_in.application_id, current_user.id)

    # Check if company info already exists for this application
    existing_company_info = await session.exec(
        select(CompanyInfo).where(CompanyInfo.application_id == company_info_in.application_id)
    )
    if existing_company_info.first():
        raise HTTPException(status_code=400, detail="Company information already exists for this application.")

    company_info = CompanyInfo.model_validate(company_info_in) # Use model_validate for Pydantic v2
    session.add(company_info)
    
    # Update application step to 5 (Directors) if it's less than 5
    application = await session.get(Application, company_info_in.application_id)
    if application and application.current_step < 5:
        application.current_step = 5
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

@router.get("/{application_id}", response_model=CompanyInfoRead)
async def read_company_info(
    *,
    session: AsyncSession = Depends(deps.get_session),
    application_id: int,
    current_user: User = Depends(deps.get_current_user),
):
    """
    Retrieve company information for a specific application.
    """
    await verify_application_ownership(session, application_id, current_user.id)

    company_info = await session.exec(
        select(CompanyInfo).where(CompanyInfo.application_id == application_id)
    )
    result = company_info.first()
    if not result:
        raise HTTPException(status_code=404, detail="Company information not found for this application.")
    return result

@router.patch("/{application_id}", response_model=CompanyInfoRead)
async def update_company_info(
    *,
    session: AsyncSession = Depends(deps.get_session),
    application_id: int,
    company_info_in: CompanyInfoUpdate,
    current_user: User = Depends(deps.get_current_user),
):
    """
    Update company information for a specific application.
    """
    await verify_application_ownership(session, application_id, current_user.id)

    company_info = await session.exec(
        select(CompanyInfo).where(CompanyInfo.application_id == application_id)
    )
    db_company_info = company_info.first()
    if not db_company_info:
        raise HTTPException(status_code=404, detail="Company information not found for this application.")
    
    company_info_data = company_info_in.model_dump(exclude_unset=True) # Use model_dump for Pydantic v2
    for key, value in company_info_data.items():
        setattr(db_company_info, key, value)
    
    session.add(db_company_info)
    
    # Update application step to 5 (Directors) if it's less than 5
    application = await session.get(Application, application_id)
    if application and application.current_step < 5:
        application.current_step = 5
        session.add(application)

    await session.commit()
    await session.refresh(db_company_info)
    return db_company_info
