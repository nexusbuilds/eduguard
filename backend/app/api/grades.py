from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import RedirectResponse
from app.core.security import get_current_user
from app.core.encryption import encrypt_value, decrypt_value
from app.db.database import AsyncSessionLocal
from app.models.models import Parent, GradeSync, EdsbyConfig, Child
from app.schemas.schemas import GradeSyncRead, GradeSyncCreate
from app.services.edsby_scraper import create_scraper, EdsbyAuthError, EdsbyUnavailableError
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List
from datetime import datetime, date

router = APIRouter()


async def _auto_apply_tiers_for_children(child_ids: List[int], tenant_id: str) -> List[dict]:
    """Auto-evaluate and apply access tiers for affected children."""
    from app.api.policy import auto_apply_child_tier
    results = []
    for cid in child_ids:
        try:
            result = await auto_apply_child_tier(cid, tenant_id)
            results.append(result)
        except Exception:
            # Non-critical: don't fail sync if tier application errors
            pass
    return results


async def _get_edsby_config(parent_id: int):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(EdsbyConfig).where(EdsbyConfig.parent_id == parent_id)
        )
        return result.scalars().first()


async def _clear_old_grades(session, child_id: int, tenant_id: str):
    """Remove existing Edsby-sourced grades for a child before re-sync."""
    from sqlalchemy import delete
    await session.execute(
        delete(GradeSync).where(
            GradeSync.child_id == child_id,
            GradeSync.tenant_id == tenant_id
        )
    )
    await session.commit()


async def _sync_edsby_for_parent(parent: Parent, use_mock: bool = False) -> dict:
    """Core sync logic. Discovers children from Edsby, matches to EduGuard children, stores grades per child."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(EdsbyConfig).where(EdsbyConfig.parent_id == parent.id)
        )
        config = result.scalars().first()

        if not config or not config.is_active:
            return {"status": "error", "message": "Edsby not configured"}

        if not config.sync_enabled:
            return {"status": "error", "message": "Edsby sync is disabled"}

        # Decrypt password
        try:
            password = decrypt_value(config.password_encrypted)
        except Exception as e:
            config.sync_error_message = f"Failed to decrypt password: {e}"
            await session.commit()
            return {"status": "error", "message": "Credential decryption failed"}

        # Create scraper and discover children + grades
        scraper = create_scraper(config.base_url, config.username, password, use_mock=use_mock)

        try:
            async with scraper:
                edsby_children = await scraper.scrape_all_children_grades()
        except EdsbyAuthError as e:
            config.sync_error_message = str(e)
            config.is_active = False
            await session.commit()
            return {"status": "error", "message": str(e)}
        except EdsbyUnavailableError as e:
            config.sync_error_message = str(e)
            await session.commit()
            return {"status": "error", "message": str(e)}
        except Exception as e:
            config.sync_error_message = f"Unexpected error: {e}"
            await session.commit()
            return {"status": "error", "message": f"Sync failed: {e}"}

        # Get EduGuard children for matching
        children_result = await session.execute(
            select(Child).where(Child.parent_id == parent.id, Child.tenant_id == parent.tenant_id)
        )
        edu_children = children_result.scalars().all()

        if not edu_children:
            return {"status": "error", "message": "No children found in EduGuard to sync grades to"}

        if not edsby_children:
            return {"status": "error", "message": "No children found in Edsby account"}

        # Match Edsby children to EduGuard children by name
        imported_total = 0
        matched_children = []
        matched_child_ids = []

        for edsby_child in edsby_children:
            # Find matching EduGuard child by name
            matched_edu_child = None
            edsby_name_lower = edsby_child.name.lower()
            edsby_first = edsby_name_lower.split()[0] if edsby_name_lower else ""

            for edu_child in edu_children:
                edu_full_name = f"{edu_child.first_name} {edu_child.last_name}".lower()
                edu_first = edu_child.first_name.lower()
                edu_last = edu_child.last_name.lower()
                # Priority: first name exact match, then full name contains
                if edu_first == edsby_first:
                    matched_edu_child = edu_child
                    break
                elif edu_full_name in edsby_name_lower or edsby_name_lower in edu_full_name:
                    matched_edu_child = edu_child
                    break

            # If no match and only one EduGuard child, assign to them
            if not matched_edu_child and len(edu_children) == 1:
                matched_edu_child = edu_children[0]

            if matched_edu_child:
                # Clear old grades for this child
                await _clear_old_grades(session, matched_edu_child.id, parent.tenant_id)

                # Insert new grades
                for g in edsby_child.grades:
                    new_grade = GradeSync(
                        child_id=matched_edu_child.id,
                        tenant_id=parent.tenant_id,
                        subject=g.subject,
                        grade=g.grade,
                        grade_date=g.grade_date or date.today(),
                    )
                    session.add(new_grade)
                    imported_total += 1

                matched_child_ids.append(matched_edu_child.id)
                matched_children.append({
                    "edsby_name": edsby_child.name,
                    "edu_guard_name": f"{matched_edu_child.first_name} {matched_edu_child.last_name}",
                    "grades_imported": len(edsby_child.grades),
                })

        config.last_synced_at = datetime.utcnow()
        config.sync_error_message = None
        await session.commit()

        # Auto-apply access tiers based on the new grades
        tier_updates = await _auto_apply_tiers_for_children(matched_child_ids, parent.tenant_id)

        return {
            "status": "success",
            "message": f"Imported {imported_total} grades for {len(matched_children)} children from Edsby",
            "synced_at": config.last_synced_at.isoformat(),
            "children": matched_children,
            "edsby_children_found": [c.name for c in edsby_children],
            "tier_updates": tier_updates,
        }


@router.get("/", response_model=List[GradeSyncRead])
async def list_grades(current_user: Parent = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(GradeSync).where(GradeSync.tenant_id == current_user.tenant_id)
            .options(selectinload(GradeSync.child))
        )
        return result.scalars().all()


@router.post("/", response_model=GradeSyncRead)
async def create_grade(grade_data: GradeSyncCreate, current_user: Parent = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        new_grade = GradeSync(**grade_data.model_dump(), tenant_id=current_user.tenant_id)
        session.add(new_grade)
        await session.commit()
        await session.refresh(new_grade)
        # Auto-apply tier for the affected child
        await _auto_apply_tiers_for_children([grade_data.child_id], current_user.tenant_id)
        return new_grade


@router.post("/sync")
async def sync_edsby(current_user: Parent = Depends(get_current_user)):
    """Trigger Edsby grade sync."""
    result = await _sync_edsby_for_parent(current_user, use_mock=False)
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/sync-mock")
async def sync_edsby_mock(current_user: Parent = Depends(get_current_user)):
    """Trigger mock Edsby grade sync for testing."""
    result = await _sync_edsby_for_parent(current_user, use_mock=True)
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/test-edsby")
async def test_edsby_connection(current_user: Parent = Depends(get_current_user)):
    """Test Edsby credentials without saving grades."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(EdsbyConfig).where(EdsbyConfig.parent_id == current_user.id)
        )
        config = result.scalars().first()

        if not config or not config.is_active:
            raise HTTPException(status_code=400, detail="Edsby not configured")

        try:
            password = decrypt_value(config.password_encrypted)
        except Exception:
            raise HTTPException(status_code=400, detail="Credential decryption failed")

        scraper = create_scraper(config.base_url, config.username, password, use_mock=False)

        try:
            async with scraper:
                await scraper.login()
                # Try to discover children
                children = await scraper.discover_children()
                return {
                    "status": "success",
                    "message": "Edsby connection successful",
                    "children_found": [c.name for c in children],
                }
        except EdsbyAuthError as e:
            raise HTTPException(status_code=401, detail=str(e))
        except EdsbyUnavailableError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Connection test failed: {e}")


@router.get("/integration")
async def get_edsby_status(current_user: Parent = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(EdsbyConfig).where(EdsbyConfig.parent_id == current_user.id)
        )
        config = result.scalars().first()
        if not config:
            return {"status": "not_configured", "message": "Edsby integration pending"}
        return {
            "status": "connected" if config.is_active else "disconnected",
            "base_url": config.base_url,
            "username": config.username,
            "child_name": config.child_name,
            "sync_enabled": config.sync_enabled,
            "last_synced": config.last_synced_at.isoformat() if config.last_synced_at else None,
            "error": config.sync_error_message,
        }


@router.get("/gpa/{child_id}")
async def get_child_gpa(child_id: int, current_user: Parent = Depends(get_current_user)):
    """Calculate GPA for a child based on their grades."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(GradeSync).where(
                GradeSync.child_id == child_id,
                GradeSync.tenant_id == current_user.tenant_id
            )
        )
        grades = result.scalars().all()

        if not grades:
            return {"child_id": child_id, "gpa": None, "grade_count": 0}

        numeric = []
        for g in grades:
            try:
                val = float(g.grade)
                if 0 <= val <= 100:
                    numeric.append(val)
            except (ValueError, TypeError):
                continue

        if not numeric:
            return {"child_id": child_id, "gpa": None, "grade_count": len(grades)}

        avg = round(sum(numeric) / len(numeric), 1)
        if avg >= 90:
            gpa = 4.0
        elif avg >= 80:
            gpa = 3.0 + (avg - 80) / 10
        elif avg >= 70:
            gpa = 2.0 + (avg - 70) / 10
        elif avg >= 60:
            gpa = 1.0 + (avg - 60) / 10
        else:
            gpa = 0.0

        return {
            "child_id": child_id,
            "gpa": round(gpa, 2),
            "average": avg,
            "grade_count": len(grades),
            "subjects": [g.subject for g in grades],
        }
