import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from src.core.config import settings
from src.core.correlation import CorrelationIdMiddleware
from src.core.database import Base, SessionLocal, engine
from src.core.telemetry import setup_telemetry
from src.infrastructure.persistence import models  # noqa: F401
from src.infrastructure.persistence.seed_tipos_siniestro import sembrar_tipos_siniestro
from src.domain.siniestros.errores import ErrorSiniestro
from src.presentation.errors import error_siniestro_handler
from src.presentation.routers import evidencias, health, siniestros

logger = logging.getLogger(__name__)


async def _sembrar_catalogo() -> None:
    """Carga idempotente de `tipo_siniestro`; si falla, el servicio arranca igual y lo registra."""
    try:
        async with SessionLocal() as session:
            await sembrar_tipos_siniestro(session)
            await session.commit()
    except Exception:
        logger.warning("No se pudo sembrar el catálogo de tipos de siniestro.", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with engine.begin() as conn:
        await conn.execute(text("SELECT pg_advisory_xact_lock(1397705812, 4)"))
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS insuranceclaims"))
        await conn.run_sync(Base.metadata.create_all)
    if settings.SEED_ON_STARTUP:
        await _sembrar_catalogo()
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
app.add_middleware(CorrelationIdMiddleware, service="insuranceclaims_service")


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


app.add_exception_handler(ErrorSiniestro, error_siniestro_handler)

app.include_router(health.router)
app.include_router(siniestros.router, prefix=settings.API_PREFIX)
app.include_router(siniestros.router_tipos, prefix=settings.API_PREFIX)
app.include_router(evidencias.router, prefix=settings.API_PREFIX)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Solventa Insurance Claims Service"}
