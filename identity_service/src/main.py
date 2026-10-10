import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.core.config import settings
from src.core.database import Base, engine
from src.core.telemetry import setup_telemetry
from src.infrastructure.persistence import models  # noqa: F401
from src.presentation.routers import health

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception:
        logger.warning(
            "No se pudo crear el esquema en el arranque; "
            "las migraciones Alembic son la fuente de verdad.",
            exc_info=True,
        )
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

setup_telemetry(app)

app.include_router(health.router, prefix=settings.API_PREFIX)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Solventa Identity Service"}