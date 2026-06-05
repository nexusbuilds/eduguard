from fastapi import APIRouter, Depends, HTTPException
from app.core.security import verify_jwt_token
from app.db.database import AsyncSessionLocal
from app.models.models import Chore
from app.schemas.schemas import ChoreCreate, Chore

router = APIRouter(dependencies=[Depends(verify_jwt_token)])

@router.post("/")
async def create_chore(chore: ChoreCreate):
    # Implementation
    pass

@router.get("/")
async def get_chores():
    # Implementation
    pass