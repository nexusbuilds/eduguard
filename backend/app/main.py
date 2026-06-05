from fastapi import FastAPI, Request, Depends, HTTPException
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
from sqlalchemy import select

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

# --- API routers ---
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(parents_router, prefix="/api/parents", tags=["parents"])
app.include_router(children_router, prefix="/api/children", tags=["children"])
app.include_router(devices_router, prefix="/api/devices", tags=["devices"])
app.include_router(grades_router, prefix="/api/grades", tags=["grades"])
app.include_router(chores_router, prefix="/api/chores", tags=["chores"])
app.include_router(precommitment_router, prefix="/api/precommitment", tags=["precommitment"])
