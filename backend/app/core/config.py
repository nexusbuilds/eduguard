from pydantic_settings import BaseSettings
from typing import List, Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "EduGuard"
    PROJECT_DESCRIPTION: str = "Parental internet control SaaS"
    PROJECT_VERSION: str = "1.0.0"
    DATABASE_URL: str = "sqlite+aiosqlite:///./eduguard.db"
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440
    CORS_ORIGINS: List[str] = ["*"]
    WG_HOST: str = "wg-easy"
    WG_PORT: int = 51821
    WG_PASSWORD: str = "admin"
    EDSBY_BASE_URL: str = ""
    EDSBY_API_KEY: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()