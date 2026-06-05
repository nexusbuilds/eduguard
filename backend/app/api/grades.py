from fastapi import APIRouter, Depends, HTTPException
from app.core.security import get_current_user
from app.db.database import AsyncSessionLocal
from app.models.models import Parent, GradeSync
from app.schemas.schemas import GradeSyncRead, GradeSyncCreate
from sqlalchemy import select
from typing import List

router = APIRouter()

@router.get("/", response_model=List[GradeSyncRead])
async def list_grades(current_user: Parent = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(GradeSync).where(GradeSync.tenant_id == current_user.tenant_id)
        )
        return result.scalars().all()

@router.post("/", response_model=GradeSyncRead)
async def create_grade(grade_data: GradeSyncCreate, current_user: Parent = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        new_grade = GradeSync(**grade_data.model_dump(), tenant_id=current_user.tenant_id)
        session.add(new_grade)
        await session.commit()
        await session.refresh(new_grade)
        return new_grade

@router.get("/integration")
async def get_edsby_status(current_user: Parent = Depends(get_current_user)):
    return {"status": "not_configured", "message": "Edsby integration pending"}
