from fastapi import APIRouter, Depends, HTTPException
from app.core.security import verify_jwt_token
from app.db.database import AsyncSessionLocal
from app.models.models import Device
from app.schemas.schemas import Device, DeviceCreate
from sqlalchemy import select

router = APIRouter(dependencies=[Depends(verify_jwt_token)])

@router.post("/")
async def create_device(device_data: DeviceCreate):
    # Implementation
    pass

@router.get("/")
async def get_devices():
    # Implementation
    pass