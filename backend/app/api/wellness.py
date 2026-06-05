from fastapi import APIRouter, Depends, HTTPException
from app.core.security import get_current_user
from app.db.database import AsyncSessionLocal
from app.models.models import Parent
from sqlalchemy import select
from typing import List
from pydantic import BaseModel

router = APIRouter()

class Counselor(BaseModel):
    id: int
    name: str
    specialty: str
    location: str
    accepts_ohip: bool
    accepts_insurance: bool
    phone: str
    email: str
    is_verified: bool

COUNSELORS_DB = [
    {"id": 1, "name": "Dr. Sarah Chen", "specialty": "Adolescent Anxiety & Screen Addiction", "location": "Toronto, ON", "accepts_ohip": True, "accepts_insurance": True, "phone": "(416) 555-0101", "email": "s.chen@example.com", "is_verified": True},
    {"id": 2, "name": "Mark Thompson, RP", "specialty": "Family Therapy & Digital Wellness", "location": "Ottawa, ON", "accepts_ohip": False, "accepts_insurance": True, "phone": "(613) 555-0202", "email": "m.thompson@example.com", "is_verified": True},
    {"id": 3, "name": "Dr. Amara Patel", "specialty": "Child Psychology & Academic Coaching", "location": "Mississauga, ON", "accepts_ohip": True, "accepts_insurance": False, "phone": "(905) 555-0303", "email": "a.patel@example.com", "is_verified": True},
    {"id": 4, "name": "Jennifer Walsh, MSW", "specialty": "Parent Coaching & Behavior Support", "location": "Hamilton, ON", "accepts_ohip": True, "accepts_insurance": True, "phone": "(905) 555-0404", "email": "j.walsh@example.com", "is_verified": False},
]

@router.get("/counselors")
async def list_counselors(location: str = None, accepts_ohip: bool = None, current_user: Parent = Depends(get_current_user)):
    results = COUNSELORS_DB
    if location:
        results = [c for c in results if location.lower() in c["location"].lower()]
    if accepts_ohip is not None:
        results = [c for c in results if c["accepts_ohip"] == accepts_ohip]
    return results

@router.post("/rule-change-request")
async def request_rule_change(child_id: int, reason: str, counselor_id: int, current_user: Parent = Depends(get_current_user)):
    # Placeholder: in production, this would notify the parent and log the request
    return {"status": "pending", "message": "Rule change request submitted. Parent notification sent.", "request_id": 1}
