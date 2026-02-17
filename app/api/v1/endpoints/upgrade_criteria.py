from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select, asc
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api import deps
from app.db.session import get_session
from app.models.user import User
from app.models.upgrade_criteria import UpgradeCriteria, UpgradeCriteriaCreate, UpgradeCriteriaRead, UpgradeCriteriaUpdate

router = APIRouter()


@router.get("/", response_model=List[UpgradeCriteriaRead])
async def list_upgrade_criteria(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(deps.get_current_user),
) -> List[UpgradeCriteriaRead]:
    """List all upgrade criteria (for applicants and admin)."""
    result = await session.exec(
        select(UpgradeCriteria).order_by(asc(UpgradeCriteria.sort_order), asc(UpgradeCriteria.id))
    )
    return list(result.all())


@router.post("/", response_model=UpgradeCriteriaRead)
async def create_upgrade_criteria(
    body: UpgradeCriteriaCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(deps.get_current_active_admin),
) -> UpgradeCriteriaRead:
    """Add a new upgrade criteria item (admin only)."""
    item = UpgradeCriteria.model_validate(body)
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


@router.patch("/{item_id}", response_model=UpgradeCriteriaRead)
async def update_upgrade_criteria(
    item_id: int,
    body: UpgradeCriteriaUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(deps.get_current_active_admin),
) -> UpgradeCriteriaRead:
    """Update an upgrade criteria item (admin only)."""
    item = await session.get(UpgradeCriteria, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(item, k, v)
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


@router.delete("/{item_id}", status_code=204)
async def delete_upgrade_criteria(
    item_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(deps.get_current_active_admin),
) -> None:
    """Delete an upgrade criteria item (admin only)."""
    item = await session.get(UpgradeCriteria, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    await session.delete(item)
    await session.commit()
