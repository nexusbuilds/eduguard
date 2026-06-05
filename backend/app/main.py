from fastapi import FastAPI, Request, Depends, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from app.core.config import settings
from app.core.tenant import TenantMiddleware
from app.core.security import verify_jwt_token
from app.db.database import init_db, AsyncSessionLocal
from app.models.models import Parent
from app.api.auth import router as auth_router
from app.api.parents import router as parents_router
from app.api.children import router as children_router
from app.api.devices import router as devices_router
from app.api.grades import router as grades_router
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

@app.on_event("startup")
async def startup():
    await init_db()

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
    return templates.TemplateResponse(request=request, name="dashboard.html", context={"user": user})

@app.get("/children")
async def children_page(request: Request):
    user = await get_user_from_cookie(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(request=request, name="children.html", context={"user": user})

@app.get("/devices")
async def devices_page(request: Request):
    user = await get_user_from_cookie(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(request=request, name="devices.html", context={"user": user})

@app.get("/chores")
async def chores_page(request: Request):
    user = await get_user_from_cookie(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(request=request, name="chores.html", context={"user": user})

@app.get("/grades")
async def grades_page(request: Request):
    user = await get_user_from_cookie(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(request=request, name="grades.html", context={"user": user})

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
    async with AsyncSessionLocal() as session:
        gd = date.fromisoformat(grade_date) if grade_date else None
        new_grade = GradeSync(child_id=child_id, subject=subject, grade=grade, grade_date=gd, tenant_id=user.tenant_id)
        session.add(new_grade)
        await session.commit()
    return RedirectResponse(url="/grades", status_code=302)

@app.post("/edsby/configure")
async def configure_edsby_form(request: Request, base_url: str = Form(...), username: str = Form(...), password: str = Form(...)):
    user = await get_user_from_cookie(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from app.models.models import EdsbyConfig
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(EdsbyConfig).where(EdsbyConfig.parent_id == user.id))
        config = result.scalars().first()
        if config:
            config.base_url = base_url
            config.username = username
            config.password_encrypted = password[:50]
            config.is_active = True
        else:
            config = EdsbyConfig(parent_id=user.id, tenant_id=user.tenant_id, base_url=base_url, username=username, password_encrypted=password[:50], is_active=True)
            session.add(config)
        await session.commit()
    return RedirectResponse(url="/grades", status_code=302)
