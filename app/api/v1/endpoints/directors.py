from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api import deps
from app.models.application import Application
from app.models.director import Director, DirectorCreate, DirectorRead
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

@router.post("/", response_model=DirectorRead)
async def create_director(
    *,
    session: AsyncSession = Depends(deps.get_session),
    director_in: DirectorCreate,
    current_user: User = Depends(deps.get_current_user),
):
    """
    Add a director to an application.
    """
    await verify_application_ownership(session, director_in.application_id, current_user.id)

    director = Director.model_validate(director_in)
    session.add(director)
    
    # Update application step to 6 (Documents) if it's less than 6
    application = await session.get(Application, director_in.application_id)
    if application and application.current_step < 6:
        application.current_step = 6
        session.add(application)

    await session.commit()
    await session.refresh(director)
    return director

@router.get("/latest/data", response_model=List[DirectorRead])
async def read_latest_directors(
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
):
    """
    Get directors from the user's most recent application that has directors.
    """
    # 1. Find user's applications
    app_query = select(Application).where(Application.user_id == current_user.id).order_by(Application.created_at.desc())
    apps = await session.exec(app_query)
    all_apps = apps.all()
    
    # 2. Iterate to find first one with directors
    for app in all_apps:
        directors_query = select(Director).where(Director.application_id == app.id)
        directors_result = await session.exec(directors_query)
        directors = directors_result.all()
        if directors:
            return directors
            
    return [] # Return empty list if no previous directors found

@router.get("/{application_id}", response_model=List[DirectorRead])
async def read_directors(
    *,
    session: AsyncSession = Depends(deps.get_session),
    application_id: int,
    current_user: User = Depends(deps.get_current_user),
):
    """
    List directors for a specific application.
    """
    await verify_application_ownership(session, application_id, current_user.id)

    directors = await session.exec(
        select(Director).where(Director.application_id == application_id)
    )
    return directors.all()

@router.delete("/{director_id}", status_code=204)
async def delete_director(
    *,
    session: AsyncSession = Depends(deps.get_session),
    director_id: int,
    current_user: User = Depends(deps.get_current_user),
):
    """
    Delete a director.
    """
    director = await session.get(Director, director_id)
    if not director:
        raise HTTPException(status_code=404, detail="Director not found")
    
    # Verify ownership via application
    await verify_application_ownership(session, director.application_id, current_user.id)
    
    await session.delete(director)
    await session.commit()
