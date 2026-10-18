import logging

from fastapi import FastAPI

from src.core.config import settings
from src.core.telemetry import setup_telemetry
from src.presentation.routers import clientes, consentimientos, health

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
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
    return {"message": "Solventa BFF Web"}