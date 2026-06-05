from fastapi import APIRouter, Depends, HTTPException, status
from app.core.security import get_current_user, verify_jwt_token
from app.db.database import AsyncSessionLocal
from app.models.models import Parent, Child
from app.schemas.schemas import ChildRead, ChildCreate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

router = APIRouter()

@router.get("/dashboard", response_model=List[ChildRead])
async def get_children(current_user: Parent = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Child).where(Child.parent_id == current_user.id))
        children = result.scalars().all()
        return children

@router.post("/children", response_model=ChildRead)
async def create_child(child_data: ChildCreate, current_user: Parent = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        new_child = Child(**child_data.model_dump(), parent_id=current_user.id, tenant_id=current_user.tenant_id)
        session.add(new_child)
        await session.commit()
        await session.refresh(new_child)
        return new_child
