from fastapi import APIRouter, Depends, HTTPException
from app.core.security import get_current_user
from app.db.database import AsyncSessionLocal
from app.models.models import Parent, GradeSync, EdsbyConfig, Child
from app.schemas.schemas import GradeSyncRead, GradeSyncCreate
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List
from datetime import datetime

router = APIRouter()

async def simulate_edsby_sync(parent_id: int, tenant_id: str):
    """Stub: simulates Edsby grade scraping. In production, use Playwright or PyEdsby."""
    async with AsyncSessionLocal() as session:
        # Get stored Edsby config
        config_result = await session.execute(
            select(EdsbyConfig).where(EdsbyConfig.parent_id == parent_id)
        )
        config = config_result.scalars().first()
        if not config or not config.is_active:
            return {"status": "error", "message": "Edsby not configured"}

        # Get children for this parent
        children_result = await session.execute(
            select(Child).where(Child.parent_id == parent_id, Child.tenant_id == tenant_id)
        )
        children = children_result.scalars().all()

        subjects = ["Math", "Science", "English", "History", "Art"]
        imported = 0
        for child in children:
            # Simulate 3-5 grades per child
            import random
            random.seed(child.id)
            for subject in random.sample(subjects, k=random.randint(2, 4)):
                grade_val = random.randint(65, 98)
                new_grade = GradeSync(
                    child_id=child.id,
                    tenant_id=tenant_id,
                    subject=subject,
                    grade=str(grade_val),
                    grade_date=datetime.utcnow().date(),
                )
                session.add(new_grade)
                imported += 1

        config.last_synced_at = datetime.utcnow()
        await session.commit()
        return {
            "status": "success",
            "message": f"Imported {imported} grades from Edsby",
            "synced_at": config.last_synced_at.isoformat()
        }

@router.get("/", response_model=List[GradeSyncRead])
async def list_grades(current_user: Parent = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(GradeSync).where(GradeSync.tenant_id == current_user.tenant_id)
            .options(selectinload(GradeSync.child))
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

@router.post("/sync")
async def sync_edsby(current_user: Parent = Depends(get_current_user)):
    """Trigger Edsby grade sync."""
    result = await simulate_edsby_sync(current_user.id, current_user.tenant_id)
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    return result

@router.get("/integration")
async def get_edsby_status(current_user: Parent = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(EdsbyConfig).where(EdsbyConfig.parent_id == current_user.id)
        )
        config = result.scalars().first()
        if not config:
            return {"status": "not_configured", "message": "Edsby integration pending"}
        return {
            "status": "connected" if config.is_active else "disconnected",
            "base_url": config.base_url,
            "username": config.username,
            "last_synced": config.last_synced_at.isoformat() if config.last_synced_at else None
        }
