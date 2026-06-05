from fastapi import APIRouter, Depends, HTTPException
from app.core.security import get_current_user
from app.db.database import AsyncSessionLocal
from app.models.models import Parent, Child, GradeSync, Chore
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

class PolicyResult(BaseModel):
    child_id: int
    child_name: str
    recommended_tier: str
    reason: str
    grade_average: Optional[float]
    chores_completed_ratio: Optional[float]

async def evaluate_child_tier(child_id: int, tenant_id: str) -> PolicyResult:
    async with AsyncSessionLocal() as session:
        child_result = await session.execute(select(Child).where(Child.id == child_id, Child.tenant_id == tenant_id))
        child = child_result.scalars().first()
        if not child:
            raise HTTPException(status_code=404, detail="Child not found")
        grades_result = await session.execute(select(GradeSync).where(GradeSync.child_id == child_id))
        grades = grades_result.scalars().all()
        avg_grade = None
        if grades:
            try:
                avg_grade = sum(float(g.grade) for g in grades if g.grade.isdigit()) / len([g for g in grades if g.grade.isdigit()])
            except:
                avg_grade = None
        chores_result = await session.execute(select(Chore).where(Chore.child_id == child_id))
        chores = chores_result.scalars().all()
        total = len(chores)
        completed = len([c for c in chores if c.is_completed and c.verified_by_parent])
        ratio = completed / total if total > 0 else 1.0
        if avg_grade is not None and avg_grade >= 80 and ratio >= 0.8:
            tier = "full"
            reason = f"Excellent grades ({avg_grade:.0f}%) and {completed}/{total} chores completed"
        elif avg_grade is not None and avg_grade >= 65 and ratio >= 0.5:
            tier = "limited"
            reason = f"Good grades ({avg_grade:.0f}%) and {completed}/{total} chores completed"
        else:
            tier = "research_only"
            reason = f"Needs improvement"
        return PolicyResult(
            child_id=child.id,
            child_name=f"{child.first_name} {child.last_name}",
            recommended_tier=tier,
            reason=reason,
            grade_average=avg_grade,
            chores_completed_ratio=ratio
        )

@router.get("/evaluate/{child_id}", response_model=PolicyResult)
async def evaluate_policy(child_id: int, current_user: Parent = Depends(get_current_user)):
    return await evaluate_child_tier(child_id, current_user.tenant_id)

@router.get("/evaluate-all")
async def evaluate_all(current_user: Parent = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Child).where(Child.parent_id == current_user.id))
        children = result.scalars().all()
        return [await evaluate_child_tier(c.id, current_user.tenant_id) for c in children]

@router.post("/apply/{child_id}")
async def apply_policy(child_id: int, tier: str, current_user: Parent = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Child).where(Child.id == child_id, Child.parent_id == current_user.id))
        child = result.scalars().first()
        if not child:
            raise HTTPException(status_code=404, detail="Child not found")
        child.access_level = tier
        await session.commit()
        return {"message": f"Access tier updated to {tier}", "child_id": child_id}
