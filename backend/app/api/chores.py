from fastapi import APIRouter, Depends, HTTPException, Request
from app.core.security import get_current_user
from app.db.database import AsyncSessionLocal
from app.models.models import Parent, Chore, Child
from app.schemas.schemas import ChoreRead, ChoreCreate
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List
from datetime import datetime

router = APIRouter()

from app.core.proxy import apply_tier_rules, TIER_RULES
from app.core.wg_easy import wg_client
from app.models.models import Device

async def reevaluate_child_tier(child_id: int, tenant_id: str):
    """Re-evaluate and apply tier after chore verification."""
    from app.api.policy import evaluate_child_tier
    result = await evaluate_child_tier(child_id, tenant_id)
    async with AsyncSessionLocal() as session:
        child_result = await session.execute(
            select(Child).where(Child.id == child_id, Child.tenant_id == tenant_id)
        )
        child = child_result.scalars().first()
        if child and child.access_level != result.recommended_tier:
            child.access_level = result.recommended_tier
            await session.commit()
            # Apply proxy rules
            device_result = await session.execute(
                select(Device).where(Device.child_id == child_id)
            )
            devices = device_result.scalars().all()
            device_ids = [d.id for d in devices]
            proxy_result = await apply_tier_rules(child_id, result.recommended_tier, device_ids)
            return {
                "tier_result": result,
                "proxy_update": proxy_result
            }
    return {"tier_result": result}

@router.get("/", response_model=List[ChoreRead])
async def list_chores(current_user: Parent = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Chore).where(Chore.tenant_id == current_user.tenant_id)
            .options(selectinload(Chore.child))
        )
        return result.scalars().all()

@router.post("/", response_model=ChoreRead)
async def create_chore(chore_data: ChoreCreate, current_user: Parent = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        new_chore = Chore(**chore_data.model_dump(), tenant_id=current_user.tenant_id)
        session.add(new_chore)
        await session.commit()
        await session.refresh(new_chore)
        return new_chore

@router.post("/{chore_id}/complete")
async def complete_chore(chore_id: int, current_user: Parent = Depends(get_current_user)):
    """Kid marks chore as completed (no auth check — kid-facing endpoint)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Chore).where(Chore.id == chore_id, Chore.tenant_id == current_user.tenant_id)
        )
        chore = result.scalars().first()
        if not chore:
            raise HTTPException(status_code=404, detail="Chore not found")
        chore.is_completed = True
        chore.completed_at = datetime.utcnow()
        await session.commit()
        return {"message": "Chore marked as completed", "chore_id": chore_id}

@router.post("/{chore_id}/verify")
async def verify_chore(chore_id: int, current_user: Parent = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Chore).where(Chore.id == chore_id, Chore.tenant_id == current_user.tenant_id)
            .options(selectinload(Chore.child))
        )
        chore = result.scalars().first()
        if not chore:
            raise HTTPException(status_code=404, detail="Chore not found")
        chore.verified_by_parent = True
        await session.commit()
        # Trigger tier re-evaluation
        if chore.child_id:
            tier_result = await reevaluate_child_tier(chore.child_id, current_user.tenant_id)
            tr = tier_result.get("tier_result")
            return {
                "message": "Chore verified",
                "chore_id": chore_id,
                "tier_update": {
                    "child_id": chore.child_id,
                    "new_tier": tr.recommended_tier if tr else "unknown",
                    "reason": tr.reason if tr else "N/A"
                }
            }
        return {"message": "Chore verified", "chore_id": chore_id}
