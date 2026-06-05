from fastapi import APIRouter, Depends, HTTPException
from app.core.security import get_current_user
from app.db.database import AsyncSessionLocal
from app.models.models import Parent, Child
from app.schemas.schemas import ChildRead, ChildCreate
from sqlalchemy import select
from typing import List

router = APIRouter()

@router.get("/", response_model=List[ChildRead])
async def list_children(current_user: Parent = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Child).where(Child.parent_id == current_user.id, Child.tenant_id == current_user.tenant_id)
        )
        return result.scalars().all()

@router.get("/{child_id}", response_model=ChildRead)
async def get_child(child_id: int, current_user: Parent = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Child).where(Child.id == child_id, Child.parent_id == current_user.id)
        )
        child = result.scalars().first()
        if not child:
            raise HTTPException(status_code=404, detail="Child not found")
        return child

@router.put("/{child_id}", response_model=ChildRead)
async def update_child(child_id: int, child_data: ChildCreate, current_user: Parent = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Child).where(Child.id == child_id, Child.parent_id == current_user.id)
        )
        child = result.scalars().first()
        if not child:
            raise HTTPException(status_code=404, detail="Child not found")
        for key, value in child_data.model_dump(exclude_unset=True).items():
            setattr(child, key, value)
        await session.commit()
        await session.refresh(child)
        return child

@router.delete("/{child_id}")
async def delete_child(child_id: int, current_user: Parent = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Child).where(Child.id == child_id, Child.parent_id == current_user.id)
        )
        child = result.scalars().first()
        if not child:
            raise HTTPException(status_code=404, detail="Child not found")
        await session.delete(child)
        await session.commit()
        return {"message": "Child deleted"}
