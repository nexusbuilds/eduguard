from fastapi import APIRouter, Depends, HTTPException, status
from app.core.security import verify_jwt_token
from app.db.database import AsyncSessionLocal
from app.models.models import Parent, Child
from app.schemas.schemas import Child, ChildCreate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

router = APIRouter(dependencies=[Depends(verify_jwt_token)])

@router.get("/dashboard", response_model=List[Child])
async def get_children(current_user: Parent = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Child).where(Child.parent_id == current_user.id))
        children = result.scalars().all()
        return children

@router.post("/children", response_model=Child)
async def create_child(child_data: ChildCreate, current_user: Parent = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        new_child = Child(**child_data.dict(), parent_id=current_user.id)
        session.add(new_child)
        await session.commit()
        await session.refresh(new_child)
        return new_child

# Helper function to get current user
async def get_current_user(token: str = Depends(oauth2_scheme)):
    payload = verify_jwt_token(token)
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Parent).where(Parent.id == payload['user_id']))
        user = result.scalars().first()
        if user.tenant_id != payload['tenant_id']:
            raise HTTPException(status_code=403, detail="Tenant mismatch")
        return user