from fastapi import APIRouter, Depends, HTTPException
from app.core.security import verify_jwt_token
from app.db.database import AsyncSessionLocal
from app.models.models import GradeSync
from app.schemas.schemas import GradeSyncCreate

router = APIRouter(dependencies=[Depends(verify_jwt_token)])

@router.post("/")
async def sync_grades(grade_data: GradeSyncCreate):
    # Implementation
    pass