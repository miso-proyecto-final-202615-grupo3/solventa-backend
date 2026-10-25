import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import grpc
import httpx
from fastapi import FastAPI
from redis.asyncio import Redis

from src.application.use_cases.generar_cotizacion_use_case import (
    GenerarCotizacionUseCase,
)
from src.core.config import settings
from src.core.telemetry import setup_telemetry
from src.infrastructure.cache.open_data_redis_cache import OpenDataRedisCache
from src.infrastructure.gateways.open_data_http_client import OpenDataHttpClient
from src.infrastructure.gateways.perfilamiento_grpc_client import (
    PerfilamientoGrpcClient,
)
from src.presentation.routers import cotizaciones, health

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    open_data_http = httpx.AsyncClient(
        timeout=settings.OPEN_DATA_TIMEOUT_SECONDS
    )
    grpc_channel = grpc.aio.insecure_channel(settings.IDENTITY_GRPC_TARGET)
    redis = Redis.from_url(
        settings.REDIS_ENDPOINT,
        password=settings.REDIS_AUTH_TOKEN or None,
        decode_responses=True,
        socket_connect_timeout=0.1,
        socket_timeout=0.1,
    )
    app.state.generar_cotizacion_use_case = GenerarCotizacionUseCase(
        perfil_financiero_provider=PerfilamientoGrpcClient(
            grpc_channel, settings.IDENTITY_GRPC_TIMEOUT_SECONDS
        ),
        open_data_provider=OpenDataHttpClient(open_data_http),
        open_data_cache=OpenDataRedisCache(
            redis, settings.OPEN_DATA_CACHE_TTL_SECONDS
        ),
    )
    try:
        yield
    finally:
        await open_data_http.aclose()
        await grpc_channel.close()
        await redis.aclose()


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
app.include_router(cotizaciones.router, prefix=settings.API_PREFIX)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Solventa Motor de Cotización"}
