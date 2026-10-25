import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import uuid

import grpc
from fastapi import FastAPI
import httpx
from sqlalchemy import text

from src.application.use_cases.obtener_perfil_financiero_use_case import (
    ObtenerPerfilFinancieroUseCase,
)
from src.core.config import settings
from src.core.database import Base, SessionLocal, engine
from src.core.telemetry import setup_telemetry
from src.infrastructure.gateways.open_finance_http_client import (
    OpenFinanceHttpClient,
)
from src.infrastructure.grpc import perfilamiento_pb2_grpc
from src.infrastructure.grpc.perfilamiento_server import (
    PerfilamientoGrpcService,
)
from src.infrastructure.persistence.cliente_repository_impl import (
    SqlAlchemyClienteRepository,
)
from src.infrastructure.persistence.consentimiento_repository_impl import (
    SqlAlchemyConsentimientoRepository,
)
from src.infrastructure.persistence import models  # noqa: F401
from src.presentation.dependencies import cerrar_consentimiento_cache
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
    async with httpx.AsyncClient(
        timeout=settings.OPEN_FINANCE_TIMEOUT_SECONDS
    ) as open_finance_http:
        open_finance_client = OpenFinanceHttpClient(open_finance_http)

        async def obtener_perfil_financiero(cliente_id: uuid.UUID):
            async with SessionLocal() as session:
                use_case = ObtenerPerfilFinancieroUseCase(
                    SqlAlchemyClienteRepository(session),
                    SqlAlchemyConsentimientoRepository(session),
                    open_finance_client,
                )
                await use_case.validar_consentimiento(cliente_id)
            return await open_finance_client.obtener_perfil_financiero(
                cliente_id
            )

        grpc_server = grpc.aio.server()
        perfilamiento_pb2_grpc.add_PerfilamientoServicer_to_server(
            PerfilamientoGrpcService(obtener_perfil_financiero), grpc_server
        )
        bound_port = grpc_server.add_insecure_port(
            f"[::]:{settings.IDENTITY_GRPC_PORT}"
        )
        if bound_port == 0:
            raise RuntimeError("No se pudo abrir el puerto gRPC de perfilamiento.")
        await grpc_server.start()
        try:
            yield
        finally:
            await grpc_server.stop(grace=1)
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
