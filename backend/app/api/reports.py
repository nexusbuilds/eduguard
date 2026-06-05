from fastapi import APIRouter, Depends
from app.core.security import get_current_user
from app.models.models import Parent

router = APIRouter()

@router.get("/summary")
async def get_summary(current_user: Parent = Depends(get_current_user)):
    return {
        "total_children": 0,
        "total_devices": 0,
        "chores_completed_this_week": 0,
        "chores_pending": 0,
        "average_grade": None,
        "screen_time_today_hours": 0,
        "tier_distribution": {"full": 0, "limited": 0, "research_only": 0}
    }

@router.get("/activity")
async def get_activity(days: int = 7, current_user: Parent = Depends(get_current_user)):
    return {"activities": [], "period_days": days}
