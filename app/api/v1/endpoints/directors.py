import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api import deps
from app.models.application import Application
from app.models.director import Director, DirectorCreate, DirectorRead
from app.models.user import User

router = APIRouter()

@router.post("/", response_model=DirectorRead)
async def create_director(
    *,
    session: AsyncSession = Depends(deps.get_session),
    director_in: DirectorCreate,
    current_user: User = Depends(deps.get_current_user),
):
    """
    Add a director to an application. application_id in body is the application UUID (internal_uid).
    """
    try:
        app_uid = uuid.UUID(director_in.application_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid application ID format")
    application = await deps.get_application_by_uid(session, app_uid)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    if application.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    data = director_in.model_dump(exclude={"application_id"})
    director = Director(**data, application_id=application.id)
    session.add(director)
    
    if application.current_step < 6:
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

@router.get("/{application_uid}", response_model=List[DirectorRead])
async def read_directors(
    *,
    session: AsyncSession = Depends(deps.get_session),
    application_uid: uuid.UUID,
    current_user: User = Depends(deps.get_current_user),
):
    """
    List directors for a specific application. application_uid is the application UUID (internal_uid).
    """
    application = await deps.get_application_by_uid(session, application_uid)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    if application.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    directors = await session.exec(
        select(Director).where(Director.application_id == application.id)
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
    
    application = await session.get(Application, director.application_id)
    if not application or application.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    await session.delete(director)
    await session.commit()
