from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.core.config import settings
from app.core.tenant import TenantMiddleware
from app.db.database import init_db
from app.api.auth import router as auth_router
from app.api.parents import router as parents_router
from app.api.children import router as children_router
from app.api.devices import router as devices_router
from app.api.grades import router as grades_router
from app.api.chores import router as chores_router
from app.api.precommitment import router as precommitment_router

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

@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse(request=request, name="dashboard.html")

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(parents_router, prefix="/api/parents", tags=["parents"])
app.include_router(children_router, prefix="/api/children", tags=["children"])
app.include_router(devices_router, prefix="/api/devices", tags=["devices"])
app.include_router(grades_router, prefix="/api/grades", tags=["grades"])
app.include_router(chores_router, prefix="/api/chores", tags=["chores"])
app.include_router(precommitment_router, prefix="/api/precommitment", tags=["precommitment"])
