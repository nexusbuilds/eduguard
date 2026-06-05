from fastapi import APIRouter, Depends, HTTPException, status, Response, Body, Request
from pydantic import BaseModel
from app.core.security import get_password_hash, create_access_token, verify_password
from app.db.database import AsyncSessionLocal
from app.models.models import Parent
from app.schemas.schemas import ParentCreate, ParentRead
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

class LoginData(BaseModel):
    email: str
    password: str

@router.post("/register", response_model=ParentRead)
async def register(parent_data: ParentCreate, request: Request):
    tenant_id = getattr(request.state, 'tenant_id', 'default')
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Parent).where(Parent.email == parent_data.email))
        existing_parent = result.scalars().first()
        if existing_parent:
            raise HTTPException(status_code=400, detail="Email already registered")
        hashed_password = get_password_hash(parent_data.password)
        new_parent = Parent(
            first_name=parent_data.first_name,
            last_name=parent_data.last_name,
            email=parent_data.email,
            hashed_password=hashed_password,
            tenant_id=tenant_id
        )
        session.add(new_parent)
        await session.commit()
        await session.refresh(new_parent)
        return new_parent

@router.post("/login")
async def login(login_data: LoginData, response: Response):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Parent).where(Parent.email == login_data.email))
        parent = result.scalars().first()
        if not parent or not verify_password(login_data.password, parent.hashed_password):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        token_data = {
            "sub": parent.email,
            "user_id": parent.id,
            "tenant_id": parent.tenant_id
        }
        access_token = create_access_token(token_data)
        return {"access_token": access_token, "token_type": "bearer"}