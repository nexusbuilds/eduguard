from fastapi import APIRouter, Depends, HTTPException, status, Response, Body, Request, Form
from fastapi.responses import RedirectResponse
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

@router.post("/register-form")
async def register_form(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...)
):
    if password != confirm_password:
        return RedirectResponse(url="/register?error=password_mismatch", status_code=302)
    first_name = name.split(' ')[0]
    last_name = ' '.join(name.split(' ')[1:]) if len(name.split(' ')) > 1 else ''
    parent_data = ParentCreate(
        first_name=first_name,
        last_name=last_name,
        email=email,
        password=password
    )
    tenant_id = getattr(request.state, 'tenant_id', 'default')
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Parent).where(Parent.email == email))
        existing_parent = result.scalars().first()
        if existing_parent:
            return RedirectResponse(url="/register?error=email_exists", status_code=302)
        hashed_password = get_password_hash(password)
        new_parent = Parent(
            first_name=first_name,
            last_name=last_name,
            email=email,
            hashed_password=hashed_password,
            tenant_id=tenant_id
        )
        session.add(new_parent)
        await session.commit()
        await session.refresh(new_parent)
        token_data = {
            "sub": new_parent.email,
            "user_id": new_parent.id,
            "tenant_id": new_parent.tenant_id
        }
        access_token = create_access_token(token_data)
        response = RedirectResponse(url="/dashboard", status_code=302)
        response.set_cookie(key="access_token", value=access_token, httponly=True, samesite="lax")
        return response

@router.post("/login-form")
async def login_form(request: Request, email: str = Form(...), password: str = Form(...)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Parent).where(Parent.email == email))
        parent = result.scalars().first()
        if not parent or not verify_password(password, parent.hashed_password):
            return RedirectResponse(url="/login?error=invalid_credentials", status_code=302)
        token_data = {
            "sub": parent.email,
            "user_id": parent.id,
            "tenant_id": parent.tenant_id
        }
        access_token = create_access_token(token_data)
        response = RedirectResponse(url="/dashboard", status_code=302)
        response.set_cookie(key="access_token", value=access_token, httponly=True, samesite="lax")
        return response

@router.get("/logout")
async def logout(response: Response):
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("access_token")
    return response