from fastapi import APIRouter, Depends, HTTPException
from app.core.security import get_current_user
from app.db.database import AsyncSessionLocal
from app.models.models import Parent, Chore
from app.schemas.schemas import ChoreRead, ChoreCreate
from sqlalchemy import select
from typing import List

router = APIRouter()

@router.get("/", response_model=List[ChoreRead])
async def list_chores(current_user: Parent = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Chore).where(Chore.tenant_id == current_user.tenant_id)
        )
        return result.scalars().all()

@router.post("/", response_model=ChoreRead)
async def create_chore(chore_data: ChoreCreate, current_user: Parent = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        new_chore = Chore(**chore_data.model_dump(), tenant_id=current_user.tenant_id)
        session.add(new_chore)
        await session.commit()
        await session.refresh(new_chore)
        return new_chore

@router.post("/{chore_id}/verify")
async def verify_chore(chore_id: int, current_user: Parent = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Chore).where(Chore.id == chore_id, Chore.tenant_id == current_user.tenant_id)
        )
        chore = result.scalars().first()
        if not chore:
            raise HTTPException(status_code=404, detail="Chore not found")
        chore.verified_by_parent = True
        await session.commit()
        return {"message": "Chore verified"}
