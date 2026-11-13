import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text

from src.core.config import settings
from src.core.correlation import CorrelationIdMiddleware
from src.core.database import Base, SessionLocal, engine
from src.core.telemetry import setup_telemetry
from src.infrastructure.persistence import models  # noqa: F401
from src.infrastructure.messaging.outbox_relay import OutboxRelay
from src.infrastructure.messaging.sqs_publicador import SqsPublicadorEventos
from src.presentation.routers import health, pagos

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS payments"))
        await conn.run_sync(Base.metadata.create_all)
    relay_task = None
    if settings.PAGO_APROBADO_QUEUE_URL:
        relay = OutboxRelay(
            SessionLocal,
            SqsPublicadorEventos(),
            settings.OUTBOX_POLL_SECONDS,
            settings.OUTBOX_BATCH_SIZE,
        )
        relay_task = asyncio.create_task(relay.ejecutar())
    else:
        logger.warning("PAGO_APROBADO_QUEUE_URL no está configurada: los eventos no se publicarán.")
    try:
        yield
    finally:
        if relay_task is not None:
            relay_task.cancel()
            with suppress(asyncio.CancelledError):
                await relay_task
        await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)
setup_telemetry(app)
app.add_middleware(CorrelationIdMiddleware, service="payments_service")


@app.exception_handler(RequestValidationError)
async def validar_sin_exponer_tarjeta(request: Request, exc: RequestValidationError):
    if request.method == "POST" and request.url.path == f"{settings.API_PREFIX}/pagos":
        errores = [
            {key: value for key, value in error.items() if key not in {"input", "ctx"}}
            for error in exc.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": errores})
    return await request_validation_exception_handler(request, exc)


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
app.include_router(pagos.router, prefix=settings.API_PREFIX)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Solventa Payments Service"}
