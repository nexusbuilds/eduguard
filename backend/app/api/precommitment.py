from fastapi import APIRouter, Depends, HTTPException
from app.core.security import get_current_user
from app.db.database import AsyncSessionLocal
from app.models.models import Parent, Precommitment
from app.schemas.schemas import PrecommitmentRead, PrecommitmentCreate
from sqlalchemy import select
from typing import List

router = APIRouter()

@router.get("/", response_model=List[PrecommitmentRead])
async def list_precommitments(current_user: Parent = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Precommitment).where(Precommitment.tenant_id == current_user.tenant_id)
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
        pc.strict_mode_enabled = enabled
        await session.commit()
        return {"message": f"Strict mode {'enabled' if enabled else 'disabled'}"}
