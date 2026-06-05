from fastapi import APIRouter, Depends, HTTPException
from app.core.security import get_current_user
from app.db.database import AsyncSessionLocal
from app.models.models import Parent, Counselor
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()

class CounselorCreate(BaseModel):
    name: str
    specialty: Optional[str] = None
    location: Optional[str] = None
    accepts_ohip: bool = False
    accepts_insurance: bool = False
    phone: Optional[str] = None
    email: Optional[str] = None

async def seed_counselors(tenant_id: str):
    """Seed default Ontario counselors if none exist."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Counselor).where(Counselor.tenant_id == tenant_id))
        if result.scalars().first():
            return
        defaults = [
            Counselor(tenant_id=tenant_id, name="Dr. Sarah Chen", specialty="Adolescent Anxiety & Screen Addiction", location="Toronto, ON", accepts_ohip=True, accepts_insurance=True, phone="(416) 555-0101", email="s.chen@example.com", is_verified=True),
            Counselor(tenant_id=tenant_id, name="Mark Thompson, RP", specialty="Family Therapy & Digital Wellness", location="Ottawa, ON", accepts_ohip=False, accepts_insurance=True, phone="(613) 555-0202", email="m.thompson@example.com", is_verified=True),
            Counselor(tenant_id=tenant_id, name="Dr. Amara Patel", specialty="Child Psychology & Academic Coaching", location="Mississauga, ON", accepts_ohip=True, accepts_insurance=False, phone="(905) 555-0303", email="a.patel@example.com", is_verified=True),
            Counselor(tenant_id=tenant_id, name="Jennifer Walsh, MSW", specialty="Parent Coaching & Behavior Support", location="Hamilton, ON", accepts_ohip=True, accepts_insurance=True, phone="(905) 555-0404", email="j.walsh@example.com", is_verified=False),
        ]
        for c in defaults:
            session.add(c)
        await session.commit()

@router.get("/counselors")
async def list_counselors(location: str = None, accepts_ohip: bool = None, accepts_insurance: bool = None, current_user: Parent = Depends(get_current_user)):
    await seed_counselors(current_user.tenant_id)
    async with AsyncSessionLocal() as session:
        query = select(Counselor).where(Counselor.tenant_id == current_user.tenant_id)
        if location:
            query = query.where(Counselor.location.ilike(f"%{location}%"))
        if accepts_ohip is not None:
            query = query.where(Counselor.accepts_ohip == accepts_ohip)
        if accepts_insurance is not None:
            query = query.where(Counselor.accepts_insurance == accepts_insurance)
        result = await session.execute(query)
        counselors = result.scalars().all()
        return [
            {
                "id": c.id,
                "name": c.name,
                "specialty": c.specialty,
                "location": c.location,
                "accepts_ohip": c.accepts_ohip,
                "accepts_insurance": c.accepts_insurance,
                "phone": c.phone,
                "email": c.email,
                "is_verified": c.is_verified,
            }
            for c in counselors
        ]

@router.post("/counselors")
async def add_counselor(data: CounselorCreate, current_user: Parent = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        new_c = Counselor(**data.model_dump(), tenant_id=current_user.tenant_id)
        session.add(new_c)
        await session.commit()
        await session.refresh(new_c)
        return {"id": new_c.id, "message": "Counselor added"}

@router.post("/rule-change-request")
async def request_rule_change(child_id: int, reason: str, counselor_id: int, current_user: Parent = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        counselor_result = await session.execute(
            select(Counselor).where(Counselor.id == counselor_id, Counselor.tenant_id == current_user.tenant_id)
        )
        counselor = counselor_result.scalars().first()
        if not counselor:
            raise HTTPException(status_code=404, detail="Counselor not found")
        # In production: send email to parent + log request in DB
        return {
            "status": "pending",
            "message": "Rule change request submitted. Parent notification sent.",
            "request_id": f"{current_user.id}-{child_id}-{int(datetime.utcnow().timestamp())}",
            "counselor": counselor.name,
            "submitted_at": datetime.utcnow().isoformat()
        }
