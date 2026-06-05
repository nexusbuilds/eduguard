from fastapi import APIRouter, Depends, HTTPException
from app.core.security import get_current_user
from app.db.database import AsyncSessionLocal
from app.models.models import Parent, Precommitment, Child
from app.schemas.schemas import PrecommitmentRead, PrecommitmentCreate
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List
from datetime import datetime, timedelta

router = APIRouter()

async def check_cooling_off(pc: Precommitment) -> bool:
    """Returns True if cooling-off period has passed."""
    if not pc.strict_mode_locked_until:
        return True
    return datetime.utcnow() >= pc.strict_mode_locked_until

@router.get("/", response_model=List[PrecommitmentRead])
async def list_precommitments(current_user: Parent = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Precommitment).where(Precommitment.tenant_id == current_user.tenant_id)
            .options(selectinload(Precommitment.child))
        )
        return result.scalars().all()

@router.post("/", response_model=PrecommitmentRead)
async def create_precommitment(
    data: PrecommitmentCreate, current_user: Parent = Depends(get_current_user)
):
    async with AsyncSessionLocal() as session:
        new_pc = Precommitment(**data.model_dump(), tenant_id=current_user.tenant_id)
        session.add(new_pc)
        await session.commit()
        await session.refresh(new_pc)
        return new_pc

@router.put("/{pc_id}/strict-mode")
async def toggle_strict_mode(pc_id: int, enabled: bool, current_user: Parent = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Precommitment).where(
                Precommitment.id == pc_id, Precommitment.tenant_id == current_user.tenant_id
            )
        )
        pc = result.scalars().first()
        if not pc:
            raise HTTPException(status_code=404, detail="Precommitment not found")
        
        if enabled:
            # Enabling strict mode — set cooling-off lock
            pc.strict_mode_enabled = True
            pc.strict_mode_locked_until = datetime.utcnow() + timedelta(hours=pc.cooling_off_hours)
        else:
            # Disabling strict mode — check cooling-off
            if not await check_cooling_off(pc):
                remaining = pc.strict_mode_locked_until - datetime.utcnow()
                hours_left = int(remaining.total_seconds() / 3600)
                raise HTTPException(
                    status_code=403,
                    detail=f"Strict mode is locked. {hours_left} hours remaining in cooling-off period."
                )
            pc.strict_mode_enabled = False
            pc.strict_mode_locked_until = None
        
        await session.commit()
        return {
            "message": f"Strict mode {'enabled' if enabled else 'disabled'}",
            "pc_id": pc_id,
            "locked_until": pc.strict_mode_locked_until.isoformat() if pc.strict_mode_locked_until else None
        }

@router.post("/{pc_id}/accountability-notify")
async def notify_accountability_partner(pc_id: int, current_user: Parent = Depends(get_current_user)):
    """Notify accountability partner of rule change attempt."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Precommitment).where(
                Precommitment.id == pc_id, Precommitment.tenant_id == current_user.tenant_id
            )
        )
        pc = result.scalars().first()
        if not pc:
            raise HTTPException(status_code=404, detail="Precommitment not found")
        if not pc.accountability_partner_email:
            raise HTTPException(status_code=400, detail="No accountability partner configured")
        
        # In production: send email via SMTP
        return {
            "message": "Accountability partner notified",
            "partner_email": pc.accountability_partner_email,
            "child_id": pc.child_id,
            "status": "email_queued"
        }
