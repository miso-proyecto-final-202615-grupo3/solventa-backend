import asyncio
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
from src.presentation.consumers.tareas import crear_procesos, detener_procesos
from src.presentation.routers import emision, firmas, health, polizas

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE SCHEMA IF NOT EXISTS insurancepolicies"))
            await conn.run_sync(Base.metadata.create_all)
    except Exception:
        logger.warning(
            "No se pudo crear el esquema en el arranque.",
            exc_info=True,
        )
    tareas = [
        asyncio.create_task(proceso, name=nombre) for nombre, proceso in crear_procesos().items()
    ]
    try:
        yield
    finally:
        await detener_procesos(tareas)


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

setup_telemetry(app)
app.add_middleware(CorrelationIdMiddleware, service="insurancepolicies_service")


@app.middleware("http")
async def log_internal_errors(request, call_next):
    try:
        return await call_next(request)
    except Exception:
        logger.exception(
            "Error interno al procesar %s %s",
            request.method,
            request.url.path,
        )
        raise


app.include_router(health.router)
app.include_router(polizas.router)
app.include_router(firmas.router, prefix=settings.API_PREFIX)
app.include_router(emision.router, prefix=settings.API_PREFIX)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Solventa Insurance Policies Service"}
