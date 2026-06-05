from fastapi import APIRouter, Depends, HTTPException
from app.core.security import get_current_user
from app.db.database import AsyncSessionLocal
from app.models.models import Parent, Device
from app.schemas.schemas import DeviceRead, DeviceCreate
from sqlalchemy import select
from typing import List

router = APIRouter()

@router.get("/", response_model=List[DeviceRead])
async def list_devices(current_user: Parent = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Device).where(Device.tenant_id == current_user.tenant_id)
        )
        return result.scalars().all()

@router.post("/", response_model=DeviceRead)
async def create_device(device_data: DeviceCreate, current_user: Parent = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        new_device = Device(**device_data.model_dump(), tenant_id=current_user.tenant_id)
        session.add(new_device)
        await session.commit()
        await session.refresh(new_device)
        return new_device

@router.get("/{device_id}", response_model=DeviceRead)
async def get_device(device_id: int, current_user: Parent = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Device).where(Device.id == device_id, Device.tenant_id == current_user.tenant_id)
        )
        device = result.scalars().first()
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        return device

@router.delete("/{device_id}")
async def delete_device(device_id: int, current_user: Parent = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Device).where(Device.id == device_id, Device.tenant_id == current_user.tenant_id)
        )
        device = result.scalars().first()
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        await session.delete(device)
        await session.commit()
        return {"message": "Device deleted"}
