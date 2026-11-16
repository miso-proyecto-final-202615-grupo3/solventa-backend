import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from src.core.config import settings
from src.core.correlation import CorrelationIdMiddleware
from src.core.database import Base, engine
from src.core.telemetry import setup_telemetry
from src.infrastructure.persistence import models  # noqa: F401
from src.presentation.routers import health, socios

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with engine.begin() as conn:
        await conn.execute(text("SELECT pg_advisory_xact_lock(1397705812, 6)"))
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS partners"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text("ALTER TABLE partners.socios ADD COLUMN IF NOT EXISTS correo VARCHAR(320)")
        )
        await conn.execute(
            text(
                "UPDATE partners.socios SET correo = 'legacy-' || id::text || '@solventa.co' "
                "WHERE correo IS NULL"
            )
        )
        await conn.execute(text("ALTER TABLE partners.socios ALTER COLUMN correo SET NOT NULL"))
    try:
        yield
    finally:
        await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

setup_telemetry(app)
app.add_middleware(CorrelationIdMiddleware)


@app.middleware("http")
async def log_internal_errors(request, call_next):
    try:
        return await call_next(request)
    except Exception:
        logger.exception(
            "Error interno al procesar %s %s", request.method, request.url.path
        )
        raise


app.include_router(health.router)
app.include_router(socios.router, prefix=settings.API_PREFIX)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Solventa Partners Service"}
