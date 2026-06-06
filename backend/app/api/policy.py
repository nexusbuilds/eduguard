from fastapi import APIRouter, Depends, HTTPException
from app.core.security import get_current_user
from app.db.database import AsyncSessionLocal
from app.models.models import Parent, Child, GradeSync, Chore, DailyUsage
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
    banked_hours: int = 0
    daily_allowance_minutes: int = 0
    banked_bonus_minutes: int = 0

async def evaluate_child_tier(child_id: int, tenant_id: str) -> PolicyResult:
    from app.core.incentives import get_tier_allowance
    async with AsyncSessionLocal() as session:
        child_result = await session.execute(select(Child).where(Child.id == child_id, Child.tenant_id == tenant_id))
        child = child_result.scalars().first()
        if not child:
            raise HTTPException(status_code=404, detail="Child not found")
        grades_result = await session.execute(select(GradeSync).where(GradeSync.child_id == child_id))
        grades = grades_result.scalars().all()
        avg_grade = None
        numeric_grades = []
        if grades:
            for g in grades:
                try:
                    val = float(g.grade)
                    if 0 <= val <= 100:
                        numeric_grades.append(val)
                except (ValueError, TypeError):
                    continue
            if numeric_grades:
                avg_grade = sum(numeric_grades) / len(numeric_grades)

        chores_result = await session.execute(select(Chore).where(Chore.child_id == child_id))
        chores = chores_result.scalars().all()
        total = len(chores)
        completed = len([c for c in chores if c.is_completed and c.verified_by_parent])
        ratio = completed / total if total > 0 else 1.0

        if avg_grade is not None and avg_grade >= 80 and ratio >= 0.8:
            tier = "full"
            reason = f"Excellent grades ({avg_grade:.1f}%) and {completed}/{total} chores completed"
        elif avg_grade is not None and avg_grade >= 65 and ratio >= 0.5:
            tier = "limited"
            reason = f"Good grades ({avg_grade:.1f}%) and {completed}/{total} chores completed"
        else:
            tier = "research_only"
            if avg_grade is not None:
                reason = f"Needs improvement ({avg_grade:.1f}% average). Focus on schoolwork to earn more access."
            else:
                reason = "No grades available yet. Defaulting to research-only until performance is assessed."

        allowance = get_tier_allowance(tier, child.banked_hours or 0)

        return PolicyResult(
            child_id=child.id,
            child_name=f"{child.first_name} {child.last_name}",
            recommended_tier=tier,
            reason=reason,
            grade_average=avg_grade,
            chores_completed_ratio=ratio,
            banked_hours=child.banked_hours or 0,
            daily_allowance_minutes=allowance.total_available_minutes,
            banked_bonus_minutes=allowance.banked_bonus_minutes,
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


@router.get("/allowance/{child_id}")
async def get_allowance(child_id: int, current_user: Parent = Depends(get_current_user)):
    """Get today's time allowance and banked hours for a child."""
    from app.core.incentives import get_tier_allowance
    from datetime import date
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Child).where(Child.id == child_id, Child.parent_id == current_user.id))
        child = result.scalars().first()
        if not child:
            raise HTTPException(status_code=404, detail="Child not found")
        allowance = get_tier_allowance(child.access_level, child.banked_hours or 0, date.today())
        return {
            "child_id": child_id,
            "tier": child.access_level,
            "banked_hours": child.banked_hours or 0,
            "base_minutes": allowance.base_minutes,
            "banked_bonus_minutes": allowance.banked_bonus_minutes,
            "max_banked_use_today": allowance.max_banked_use_today,
            "total_available_minutes": allowance.total_available_minutes,
            "explanation": allowance.explanation,
        }


@router.post("/use-time/{child_id}")
async def use_time(child_id: int, minutes: int, use_banked: bool = False, current_user: Parent = Depends(get_current_user)):
    """Record full-access time usage for a child. Deducts from allowance or banked hours."""
    from app.core.incentives import get_tier_allowance
    from datetime import date
    async with AsyncSessionLocal() as session:
        child_result = await session.execute(select(Child).where(Child.id == child_id, Child.parent_id == current_user.id))
        child = child_result.scalars().first()
        if not child:
            raise HTTPException(status_code=404, detail="Child not found")

        today = date.today()
        allowance = get_tier_allowance(child.access_level, child.banked_hours or 0, today)

        # Get or create today's usage record
        usage_result = await session.execute(
            select(DailyUsage).where(DailyUsage.child_id == child_id, DailyUsage.usage_date == today)
        )
        usage = usage_result.scalars().first()
        if not usage:
            usage = DailyUsage(child_id=child_id, usage_date=today, full_access_minutes=0, banked_minutes=0)
            session.add(usage)
            await session.flush()

        # Ensure non-None values
        usage.full_access_minutes = usage.full_access_minutes or 0
        usage.banked_minutes = usage.banked_minutes or 0

        # Determine which bucket to deduct from
        if use_banked:
            available_banked = min(allowance.max_banked_use_today - usage.banked_minutes, child.banked_hours * 60)
            if minutes > available_banked:
                raise HTTPException(status_code=429, detail=f"Only {available_banked} banked minutes remaining today")
            usage.banked_minutes += minutes
            # Deduct from child's banked hour balance (convert minutes to hours, round down)
            child.banked_hours = max(0, child.banked_hours - (minutes / 60.0))
        else:
            available_base = allowance.base_minutes - usage.full_access_minutes
            if minutes > available_base:
                raise HTTPException(status_code=429, detail=f"Only {available_base} base minutes remaining today")
            usage.full_access_minutes += minutes

        await session.commit()
        return {
            "child_id": child_id,
            "used_minutes": minutes,
            "from_banked": use_banked,
            "full_access_minutes_used_today": usage.full_access_minutes,
            "banked_minutes_used_today": usage.banked_minutes,
            "remaining_banked_hours": child.banked_hours,
        }


async def auto_apply_child_tier(child_id: int, tenant_id: str) -> dict:
    """Evaluate and automatically apply the recommended access tier for a child.

    Called after grade sync or manual grade entry so access level stays in sync
    with academic performance. Also detects significant grade improvement and
    awards banked discretionary hours.
    """
    from app.core.proxy import apply_tier_rules
    from app.core.incentives import calculate_banked_hours_reward

    evaluation = await evaluate_child_tier(child_id, tenant_id)
    async with AsyncSessionLocal() as session:
        child_result = await session.execute(select(Child).where(Child.id == child_id, Child.tenant_id == tenant_id))
        child = child_result.scalars().first()
        if child:
            old_tier = child.access_level
            old_banked = child.banked_hours or 0
            old_prev_avg = float(child.previous_grade_average) if child.previous_grade_average else None
            current_avg = evaluation.grade_average

            # Update tier
            child.access_level = evaluation.recommended_tier

            # Award banked hours for significant improvement (tier upgrade)
            new_banked = old_banked
            improvement_awarded = 0
            if current_avg is not None:
                new_banked = calculate_banked_hours_reward(old_tier, evaluation.recommended_tier, old_banked)
                improvement_awarded = new_banked - old_banked
                child.banked_hours = new_banked
                child.previous_grade_average = str(round(current_avg, 2))

            await session.commit()

            # Best-effort proxy rule application
            try:
                device_ids = []
                if child.device:
                    device_ids.append(child.device.id)
                await apply_tier_rules(child.id, evaluation.recommended_tier, device_ids)
            except Exception:
                pass

            return {
                "child_id": child_id,
                "old_tier": old_tier,
                "new_tier": evaluation.recommended_tier,
                "reason": evaluation.reason,
                "grade_average": evaluation.grade_average,
                "banked_hours": new_banked,
                "improvement_awarded_hours": improvement_awarded,
                "daily_allowance_minutes": evaluation.daily_allowance_minutes,
            }
    return {"child_id": child_id, "error": "Child not found"}
