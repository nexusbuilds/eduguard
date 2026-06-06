from fastapi import FastAPI, Request, Depends, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from app.core.config import settings
from app.core.tenant import TenantMiddleware
from app.core.security import verify_jwt_token
from app.core.encryption import encrypt_value, decrypt_value
from app.db.database import init_db, AsyncSessionLocal
from app.models.models import Parent, EdsbyConfig, Child, GradeSync
from app.api.auth import router as auth_router
from app.api.parents import router as parents_router
from app.api.children import router as children_router
from app.api.devices import router as devices_router
from app.api.grades import router as grades_router, _sync_edsby_for_parent
from app.api.chores import router as chores_router
from app.api.precommitment import router as precommitment_router
from app.api.wellness import router as wellness_router
from app.api.reports import router as reports_router
from app.api.policy import router as policy_router
from sqlalchemy import select
from datetime import date

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_DESCRIPTION,
    version=settings.PROJECT_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(TenantMiddleware)

# Static files and templates
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
templates = Jinja2Templates(directory="frontend/templates")

# --- APScheduler for background Edsby sync ---
scheduler = None

@app.on_event("startup")
async def startup():
    await init_db()
    global scheduler
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        scheduler = AsyncIOScheduler()

        async def daily_sync():
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(EdsbyConfig).where(EdsbyConfig.is_active == True, EdsbyConfig.sync_enabled == True)
                )
                configs = result.scalars().all()
                for config in configs:
                    parent_result = await session.execute(
                        select(Parent).where(Parent.id == config.parent_id)
                    )
                    parent = parent_result.scalars().first()
                    if parent:
                        await _sync_edsby_for_parent(parent, use_mock=False)

        scheduler.add_job(daily_sync, CronTrigger(hour=6, minute=0), id="edsby_daily_sync", replace_existing=True)
        scheduler.start()
    except Exception as e:
        print(f"Scheduler setup failed (non-critical): {e}")

@app.on_event("shutdown")
async def shutdown():
    global scheduler
    if scheduler:
        scheduler.shutdown()

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": settings.PROJECT_NAME}

# --- Helper: get user from cookie ---
async def get_user_from_cookie(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = verify_jwt_token(token)
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Parent).where(Parent.id == payload.get("user_id")))
            user = result.scalars().first()
            if user and user.tenant_id == payload.get("tenant_id"):
                return user
    except Exception:
        pass
    return None

# --- Public pages ---
@app.get("/")
async def root(request: Request):
    user = await get_user_from_cookie(request)
    if user:
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/login")
async def login_page(request: Request):
    user = await get_user_from_cookie(request)
    if user:
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse(request=request, name="login.html")

@app.get("/register")
async def register_page(request: Request):
    user = await get_user_from_cookie(request)
    if user:
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse(request=request, name="register.html")

# --- Protected pages ---
@app.get("/dashboard")
async def dashboard(request: Request):
    user = await get_user_from_cookie(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.models.models import Child, Device, Chore, GradeSync
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select, func
    from datetime import datetime, timedelta
    async with AsyncSessionLocal() as session:
        # Children with devices
        child_result = await session.execute(
            select(Child).where(Child.parent_id == user.id, Child.tenant_id == user.tenant_id)
            .options(selectinload(Child.device))
        )
        children = child_result.scalars().all()

        # Device count
        device_result = await session.execute(select(Device).where(Device.tenant_id == user.tenant_id))
        device_count = len(device_result.scalars().all())

        # Chores done this week
        week_ago = datetime.utcnow() - timedelta(days=7)
        chores_done_result = await session.execute(
            select(Chore).where(
                Chore.tenant_id == user.tenant_id,
                Chore.is_completed == True,
                Chore.verified_by_parent == True,
                Chore.completed_at >= week_ago
            )
        )
        chores_done = len(chores_done_result.scalars().all())

        # Pending chores
        pending_result = await session.execute(
            select(Chore).where(
                Chore.tenant_id == user.tenant_id,
                Chore.is_completed == False
            )
        )
        pending_chores = len(pending_result.scalars().all())

        # Average grade
        grades = await session.execute(
            select(GradeSync).where(GradeSync.tenant_id == user.tenant_id)
        )
        all_grades = grades.scalars().all()
        avg_grade = None
        if all_grades:
            try:
                numeric = [float(g.grade) for g in all_grades if g.grade and g.grade.replace('.', '').isdigit()]
                avg_grade = round(sum(numeric) / len(numeric), 1) if numeric else None
            except:
                avg_grade = None

        # Tier distribution
        tier_counts = {"full": 0, "limited": 0, "research_only": 0}
        for c in children:
            tier_counts[c.access_level] = tier_counts.get(c.access_level, 0) + 1

        # Recent grades
        recent_grades_result = await session.execute(
            select(GradeSync).where(GradeSync.tenant_id == user.tenant_id)
            .order_by(GradeSync.synced_at.desc()).limit(5)
            .options(selectinload(GradeSync.child))
        )
        recent_grades = recent_grades_result.scalars().all()

        # Edsby config
        edsby_result = await session.execute(select(EdsbyConfig).where(EdsbyConfig.parent_id == user.id))
        edsby_config = edsby_result.scalars().first()

    return templates.TemplateResponse(request=request, name="dashboard.html", context={
        "user": user,
        "children": children,
        "device_count": device_count,
        "chores_done": chores_done,
        "pending_chores": pending_chores,
        "avg_grade": avg_grade,
        "tier_counts": tier_counts,
        "recent_grades": recent_grades,
        "edsby_config": edsby_config,
    })

@app.get("/children")
async def children_page(request: Request):
    user = await get_user_from_cookie(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.models.models import Child
    from sqlalchemy.orm import selectinload
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Child).where(Child.parent_id == user.id, Child.tenant_id == user.tenant_id)
            .options(selectinload(Child.device))
        )
        children = result.scalars().all()
    return templates.TemplateResponse(request=request, name="children.html", context={"user": user, "children": children})

@app.get("/devices")
async def devices_page(request: Request):
    user = await get_user_from_cookie(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.models.models import Device
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Device).where(Device.tenant_id == user.tenant_id))
        devices = result.scalars().all()
    return templates.TemplateResponse(request=request, name="devices.html", context={"user": user, "devices": devices})

@app.get("/chores")
async def chores_page(request: Request):
    user = await get_user_from_cookie(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.models.models import Chore, Child
    from sqlalchemy.orm import selectinload
    async with AsyncSessionLocal() as session:
        chores_result = await session.execute(
            select(Chore).where(Chore.tenant_id == user.tenant_id)
            .options(selectinload(Chore.child))
        )
        chores = chores_result.scalars().all()
        children_result = await session.execute(select(Child).where(Child.parent_id == user.id))
        children = children_result.scalars().all()
    return templates.TemplateResponse(request=request, name="chores.html", context={"user": user, "chores": chores, "children": children})

@app.get("/grades")
async def grades_page(request: Request):
    user = await get_user_from_cookie(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.models.models import GradeSync, Child, EdsbyConfig
    from sqlalchemy.orm import selectinload
    async with AsyncSessionLocal() as session:
        grades_result = await session.execute(
            select(GradeSync).where(GradeSync.tenant_id == user.tenant_id)
            .options(selectinload(GradeSync.child))
        )
        grades = grades_result.scalars().all()
        children_result = await session.execute(select(Child).where(Child.parent_id == user.id))
        children = children_result.scalars().all()
        edsby_result = await session.execute(select(EdsbyConfig).where(EdsbyConfig.parent_id == user.id))
        edsby_config = edsby_result.scalars().first()
    return templates.TemplateResponse(request=request, name="grades.html", context={"user": user, "grades": grades, "children": children, "edsby_config": edsby_config})

@app.get("/precommitment")
async def precommitment_page(request: Request):
    user = await get_user_from_cookie(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(request=request, name="precommitment.html", context={"user": user})

@app.get("/wellness")
async def wellness_page(request: Request):
    user = await get_user_from_cookie(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(request=request, name="wellness.html", context={"user": user})

@app.get("/reports")
async def reports_page(request: Request):
    user = await get_user_from_cookie(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(request=request, name="reports.html", context={"user": user})

# --- API routers ---
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(parents_router, prefix="/api/parents", tags=["parents"])
app.include_router(children_router, prefix="/api/children", tags=["children"])
app.include_router(devices_router, prefix="/api/devices", tags=["devices"])
app.include_router(grades_router, prefix="/api/grades", tags=["grades"])
app.include_router(chores_router, prefix="/api/chores", tags=["chores"])
app.include_router(precommitment_router, prefix="/api/precommitment", tags=["precommitment"])
app.include_router(wellness_router, prefix="/api/wellness", tags=["wellness"])
app.include_router(reports_router, prefix="/api/reports", tags=["reports"])
app.include_router(policy_router, prefix="/api/policy", tags=["policy"])

# --- Kid portal ---
from app.api.kid import router as kid_router
app.include_router(kid_router, prefix="/kid", tags=["kid"])

# --- Form handlers for web UI ---
@app.post("/children/add")
async def add_child_form(request: Request, first_name: str = Form(...), last_name: str = Form(...), birthdate: str = Form(None), email: str = Form(None)):
    user = await get_user_from_cookie(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.models.models import Child
    async with AsyncSessionLocal() as session:
        bd = date.fromisoformat(birthdate) if birthdate else None
        new_child = Child(first_name=first_name, last_name=last_name, birthdate=bd, email=email, parent_id=user.id, tenant_id=user.tenant_id)
        session.add(new_child)
        await session.commit()
    return RedirectResponse(url="/children", status_code=302)

@app.post("/devices/add")
async def add_device_form(request: Request, name: str = Form(...), device_type: str = Form("laptop"), mac_address: str = Form(None)):
    user = await get_user_from_cookie(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.models.models import Device
    async with AsyncSessionLocal() as session:
        new_device = Device(name=name, device_type=device_type, mac_address=mac_address, tenant_id=user.tenant_id)
        session.add(new_device)
        await session.commit()
    return RedirectResponse(url="/devices", status_code=302)

@app.post("/chores/create")
async def create_chore_form(request: Request, name: str = Form(...), description: str = Form(None), child_id: int = Form(0), reward_points: int = Form(10), due_date: str = Form(None)):
    user = await get_user_from_cookie(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.models.models import Chore
    from sqlalchemy import func
    async with AsyncSessionLocal() as session:
        dd = date.fromisoformat(due_date) if due_date else None
        cid = child_id if child_id > 0 else None
        new_chore = Chore(name=name, description=description, child_id=cid, reward_points=reward_points, due_date=dd, tenant_id=user.tenant_id)
        session.add(new_chore)
        await session.commit()
    return RedirectResponse(url="/chores", status_code=302)

@app.post("/grades/add")
async def add_grade_form(request: Request, child_id: int = Form(...), subject: str = Form(...), grade: str = Form(...), grade_date: str = Form(None)):
    user = await get_user_from_cookie(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.models.models import GradeSync
    from app.api.grades import _auto_apply_tiers_for_children
    async with AsyncSessionLocal() as session:
        gd = date.fromisoformat(grade_date) if grade_date else None
        new_grade = GradeSync(child_id=child_id, subject=subject, grade=grade, grade_date=gd, tenant_id=user.tenant_id)
        session.add(new_grade)
        await session.commit()
    # Auto-apply access tier based on the new grade
    await _auto_apply_tiers_for_children([child_id], user.tenant_id)
    return RedirectResponse(url="/grades", status_code=302)

@app.post("/edsby/configure")
async def configure_edsby_form(
    request: Request,
    base_url: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    child_name: str = Form(None),
    sync_enabled: bool = Form(False),
):
    user = await get_user_from_cookie(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(EdsbyConfig).where(EdsbyConfig.parent_id == user.id))
        config = result.scalars().first()
        encrypted_pw = encrypt_value(password)
        if config:
            config.base_url = base_url
            config.username = username
            config.password_encrypted = encrypted_pw
            config.child_name = child_name
            config.sync_enabled = sync_enabled
            config.is_active = True
            config.sync_error_message = None
        else:
            config = EdsbyConfig(
                parent_id=user.id,
                tenant_id=user.tenant_id,
                base_url=base_url,
                username=username,
                password_encrypted=encrypted_pw,
                child_name=child_name,
                sync_enabled=sync_enabled,
                is_active=True,
            )
            session.add(config)
        await session.commit()
    return RedirectResponse(url="/grades", status_code=302)

@app.get("/edsby/connect")
async def edsby_connect_page(request: Request):
    user = await get_user_from_cookie(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    async with AsyncSessionLocal() as session:
        children_result = await session.execute(
            select(Child).where(Child.parent_id == user.id, Child.tenant_id == user.tenant_id)
        )
        children = children_result.scalars().all()
        edsby_result = await session.execute(select(EdsbyConfig).where(EdsbyConfig.parent_id == user.id))
        edsby_config = edsby_result.scalars().first()
    return templates.TemplateResponse(request=request, name="edsby_connect.html", context={
        "user": user,
        "children": children,
        "edsby_config": edsby_config,
    })
