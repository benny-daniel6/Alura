from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
import logging

from app.core.config import settings
from app.core.production_checks import check_production_config
from app.api.v1.router import api_router
from app.db.base import Base
from app.db.dev_schema import add_missing_columns
from app.db.session import engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    errors, warnings = check_production_config(settings)
    for w in warnings:
        logger.warning(w)
    if errors:
        raise RuntimeError("Alura is not configured for production:\n- " + "\n- ".join(errors))

    # Setup tables in dev mode if they do not exist
    if settings.ENVIRONMENT == "development":
        async with engine.begin() as conn:
            if conn.dialect.name == "postgresql":
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(add_missing_columns)

    yield
    # Cleanup on shutdown
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    # Interactive API docs only in development; production does not advertise its endpoints
    openapi_url=f"{settings.API_V1_STR}/openapi.json" if settings.is_development else None,
    docs_url=f"{settings.API_V1_STR}/docs" if settings.is_development else None,
    redoc_url=f"{settings.API_V1_STR}/redoc" if settings.is_development else None,
    lifespan=lifespan,
    description="Backend API for Alura AI Wardrobe & Styling application."
)

# CORS setup
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        # Bearer tokens, no cookies: credentials are never needed (and "*" + credentials reflects any origin)
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path.startswith(settings.API_V1_STR):
        response.headers.setdefault("Cache-Control", "no-store")  # account data must not sit in shared caches
    return response


app.include_router(api_router, prefix=settings.API_V1_STR)

# Serve local storage static assets during development only; other environments serve from S3
if settings.ENVIRONMENT == "development":
    storage_path = Path("data/storage")
    storage_path.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(storage_path)), name="static")


@app.get("/health", tags=["System"])
async def health_check():
    return {
        "status": "healthy",
        "service": "Alura Wardrobe API",
        "environment": settings.ENVIRONMENT
    }
