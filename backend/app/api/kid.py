from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from app.db.database import AsyncSessionLocal
from app.models.models import Child, Chore, GradeSync, Device
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from datetime import datetime

router = APIRouter()

async def get_child_from_pin(request: Request):
    """Authenticate kid via PIN cookie."""
    pin = request.cookies.get("kid_pin")
    child_id = request.cookies.get("kid_id")
    if not pin or not child_id:
        return None
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Child).where(Child.id == int(child_id), Child.pin == pin)
        )
        return result.scalars().first()

@router.get("/login")
async def kid_login_page(request: Request):
    from app.main import templates
    return templates.TemplateResponse(request=request, name="kid_login.html")

@router.post("/login")
async def kid_login(request: Request, child_id: int = Form(...), pin: str = Form(...)):
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="frontend/templates")
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Child).where(Child.id == child_id, Child.pin == pin)
        )
        child = result.scalars().first()
        if not child:
            return templates.TemplateResponse(request=request, name="kid_login.html", context={"error": "Invalid PIN"})
    response = RedirectResponse(url="/kid/dashboard", status_code=302)
    response.set_cookie(key="kid_pin", value=pin, httponly=True, max_age=86400)
    response.set_cookie(key="kid_id", value=str(child_id), httponly=True, max_age=86400)
    return response

@router.get("/dashboard")
async def kid_dashboard(request: Request):
    from app.main import templates
    from app.core.incentives import get_tier_allowance
    from datetime import date
    child = await get_child_from_pin(request)
    if not child:
        return RedirectResponse(url="/kid/login", status_code=302)
    
    async with AsyncSessionLocal() as session:
        # Grades
        grades_result = await session.execute(
            select(GradeSync).where(GradeSync.child_id == child.id)
            .order_by(GradeSync.synced_at.desc())
        )
        grades = grades_result.scalars().all()
        
        # Chores
        chores_result = await session.execute(
            select(Chore).where(Chore.child_id == child.id)
            .options(selectinload(Chore.child))
        )
        chores = chores_result.scalars().all()
        
        # Devices
        devices_result = await session.execute(
            select(Device).where(Device.child_id == child.id)
        )
        devices = devices_result.scalars().all()
        
        # Calculate grade average
        avg_grade = None
        if grades:
            try:
                numeric = [float(g.grade) for g in grades if g.grade and g.grade.replace('.', '').isdigit()]
                avg_grade = round(sum(numeric) / len(numeric), 1) if numeric else None
            except:
                avg_grade = None
        
        # Time allowance
        allowance = get_tier_allowance(child.access_level, child.banked_hours or 0, date.today())
    
    return templates.TemplateResponse(request=request, name="kid_dashboard.html", context={
        "child": child,
        "grades": grades,
        "chores": chores,
        "devices": devices,
        "avg_grade": avg_grade,
        "allowance": allowance,
    })

@router.post("/chores/{chore_id}/claim")
async def claim_chore(chore_id: int, request: Request):
    """Kid marks chore as completed (claims it)."""
    child = await get_child_from_pin(request)
    if not child:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Chore).where(Chore.id == chore_id, Chore.child_id == child.id)
        )
        chore = result.scalars().first()
        if not chore:
            raise HTTPException(status_code=404, detail="Chore not found")
        
        chore.is_completed = True
        chore.completed_at = datetime.utcnow()
        await session.commit()
    
    return {"message": "Chore submitted for verification", "chore_id": chore_id}

@router.get("/logout")
async def kid_logout():
    response = RedirectResponse(url="/kid/login", status_code=302)
    response.delete_cookie("kid_pin")
    response.delete_cookie("kid_id")
    return response
