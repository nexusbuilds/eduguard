from fastapi import APIRouter, Depends
from app.core.security import get_current_user
from app.db.database import AsyncSessionLocal
from app.models.models import Parent, Child, Device, Chore, GradeSync
from sqlalchemy import select, func
from datetime import datetime, timedelta

router = APIRouter()

@router.get("/summary")
async def get_summary(current_user: Parent = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        # Children
        child_result = await session.execute(
            select(func.count(Child.id)).where(Child.parent_id == current_user.id)
        )
        total_children = child_result.scalar()

        # Devices
        device_result = await session.execute(
            select(func.count(Device.id)).where(Device.tenant_id == current_user.tenant_id)
        )
        total_devices = device_result.scalar()

        # Chores this week
        week_ago = datetime.utcnow() - timedelta(days=7)
        completed_result = await session.execute(
            select(func.count(Chore.id)).where(
                Chore.tenant_id == current_user.tenant_id,
                Chore.is_completed == True,
                Chore.verified_by_parent == True,
                Chore.completed_at >= week_ago
            )
        )
        chores_completed_this_week = completed_result.scalar()

        pending_result = await session.execute(
            select(func.count(Chore.id)).where(
                Chore.tenant_id == current_user.tenant_id,
                Chore.is_completed == False
            )
        )
        chores_pending = pending_result.scalar()

        # Average grade
        grade_result = await session.execute(
            select(GradeSync).where(GradeSync.tenant_id == current_user.tenant_id)
        )
        grades = grade_result.scalars().all()
        avg_grade = None
        if grades:
            try:
                numeric = [float(g.grade) for g in grades if g.grade and g.grade.replace('.', '').isdigit()]
                avg_grade = round(sum(numeric) / len(numeric), 1) if numeric else None
            except:
                avg_grade = None

        # Tier distribution
        tier_result = await session.execute(
            select(Child.access_level, func.count(Child.id))
            .where(Child.parent_id == current_user.id)
            .group_by(Child.access_level)
        )
        tier_rows = tier_result.all()
        tier_distribution = {"full": 0, "limited": 0, "research_only": 0}
        for row in tier_rows:
            tier_distribution[row[0]] = row[1]

        return {
            "total_children": total_children,
            "total_devices": total_devices,
            "chores_completed_this_week": chores_completed_this_week,
            "chores_pending": chores_pending,
            "average_grade": avg_grade,
            "screen_time_today_hours": 0,
            "tier_distribution": tier_distribution
        }

@router.get("/activity")
async def get_activity(days: int = 7, current_user: Parent = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        since = datetime.utcnow() - timedelta(days=days)
        # Recent grade additions
        grade_result = await session.execute(
            select(GradeSync).where(
                GradeSync.tenant_id == current_user.tenant_id,
                GradeSync.synced_at >= since
            ).order_by(GradeSync.synced_at.desc()).limit(10)
        )
        grades = grade_result.scalars().all()

        # Recent chore verifications
        chore_result = await session.execute(
            select(Chore).where(
                Chore.tenant_id == current_user.tenant_id,
                Chore.verified_by_parent == True,
                Chore.completed_at >= since
            ).order_by(Chore.completed_at.desc()).limit(10)
        )
        chores = chore_result.scalars().all()

        activities = []
        for g in grades:
            activities.append({
                "type": "grade_sync",
                "message": f"Grade synced: {g.subject} = {g.grade}%",
                "timestamp": g.synced_at.isoformat() if g.synced_at else None
            })
        for c in chores:
            activities.append({
                "type": "chore_verified",
                "message": f"Chore verified: {c.name}",
                "timestamp": c.completed_at.isoformat() if c.completed_at else None
            })
        activities.sort(key=lambda x: x["timestamp"] or "", reverse=True)
        return {"activities": activities[:20], "period_days": days}
