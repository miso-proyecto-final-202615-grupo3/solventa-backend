import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from src.core.config import settings
from src.core.database import Base, engine
from src.core.telemetry import setup_telemetry
from src.infrastructure.persistence import models  # noqa: F401
from src.presentation.dependencies import (
    abrir_gestionar_consentimiento_use_case,
    cerrar_consentimiento_cache,
)
from src.presentation.grpc.server import iniciar_servidor_grpc
from src.presentation.routers import clientes, consentimientos, health

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("CREATE SCHEMA IF NOT EXISTS identity")
            )
            await conn.run_sync(Base.metadata.create_all)
    except Exception:
        logger.warning(
            "No se pudo crear el esquema en el arranque.",
            exc_info=True,
        )
    grpc_server = None
    if settings.GRPC_ENABLED:
        grpc_server = await iniciar_servidor_grpc(
            abrir_gestionar_consentimiento_use_case, settings.GRPC_PORT
        )
    try:
        yield
    finally:
        if grpc_server is not None:
            await grpc_server.stop(grace=2)
        await cerrar_consentimiento_cache()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

setup_telemetry(app)


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
app.include_router(clientes.router, prefix=settings.API_PREFIX)
app.include_router(consentimientos.router, prefix=settings.API_PREFIX)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Solventa Identity Service"}