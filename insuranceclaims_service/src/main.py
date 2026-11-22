import logging
import asyncio
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
from src.presentation.routers import evidencias, health, operador, siniestros
from src.infrastructure.messaging.outbox_relay import OutboxRelay
from src.infrastructure.gateways.identity_destinos_client import IdentityDestinosClient
from src.infrastructure.notifications.factory import crear_notificador_push
from src.application.use_cases.notificar_cambio_estado_use_case import NotificarCambioEstadoUseCase
from src.infrastructure.gateways.polizas_factory import crear_polizas_port
from src.infrastructure.messaging.procesador_eventos_parametricos import ProcesadorEventosParametricos
from src.infrastructure.messaging.sqs_eventos_parametricos import (
    ConsumidorSqsEventosParametricos,
    bus_activo,
    crear_cliente_sqs,
)
from src.infrastructure.pagos.solicitudes_pago import crear_solicitudes_pago
from src.presentation.routers import parametricos
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


def _configurar_logs_de_la_aplicacion() -> None:
    """Sin esto los `logger.info` de `src.*` (relay y notificaciones push) se descartan: solo uvicorn tiene handler."""
    app_logger = logging.getLogger("src")
    if not app_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:     %(message)s"))
        app_logger.addHandler(handler)
    app_logger.setLevel(logging.INFO)


_configurar_logs_de_la_aplicacion()


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
    # HU4.2.2: relay del outbox → notificaciones push. Apagado por defecto (NOTIFICACIONES_HABILITADAS=false).
    # HU4.2.3: el mismo relay entrega las solicitudes de pago de indemnizaciones a Pagos.
    tareas: list[asyncio.Task] = []
    cierres = []
    notificar = None
    if settings.NOTIFICACIONES_HABILITADAS:
        try:
            notificador = crear_notificador_push(settings)
        except ValueError as exc:
            # Sin configuración (p. ej. falta el ARN de SNS) el servicio sigue funcionando; los eventos
            # quedan PENDIENTE en el outbox y se envían cuando se corrija y se reinicie.
            logger.error("notificaciones_push_sin_configurar error=%s", exc)
        else:
            cliente_destinos = IdentityDestinosClient(settings.IDENTITY_SERVICE_URL)
            cierres.append(cliente_destinos)
            notificar = NotificarCambioEstadoUseCase(cliente_destinos, notificador)
    try:
        pagos = crear_solicitudes_pago(settings)
    except ValueError as exc:
        logger.error("solicitudes_pago_sin_configurar error=%s", exc)
        pagos = None
    if pagos is not None:
        cierres.append(pagos)
    if notificar is not None or pagos is not None:
        relay = OutboxRelay(
            SessionLocal, notificar, settings.OUTBOX_INTERVALO_SEGUNDOS, settings.OUTBOX_MAX_INTENTOS, pagos=pagos
        )
        tareas.append(asyncio.create_task(relay.ejecutar()))
    if settings.EVENTOS_PARAMETRICOS_HABILITADOS:
        polizas = crear_polizas_port(settings)
        cierres.append(polizas)
        argumentos = (
            SessionLocal, polizas, lambda: datetime.now(UTC), settings.ESTADOS_POLIZA_ELEGIBLES.split(","),
            settings.EVENTOS_INTERVALO_SEGUNDOS, settings.EVENTOS_MAX_INTENTOS,
        )
        try:
            if bus_activo(settings) == "sqs":
                if not settings.EVENTOS_PARAMETRICOS_QUEUE_URL:
                    raise ValueError("Falta EVENTOS_PARAMETRICOS_QUEUE_URL para EVENTOS_BUS=sqs.")
                procesador = ConsumidorSqsEventosParametricos(
                    *argumentos,
                    client=crear_cliente_sqs(settings.AWS_REGION, settings.SQS_AWS_PROFILE, settings.SQS_ENDPOINT_URL),
                    queue_url=settings.EVENTOS_PARAMETRICOS_QUEUE_URL,
                    dlq_url=settings.EVENTOS_PARAMETRICOS_DLQ_URL,
                    espera_segundos=settings.EVENTOS_SQS_ESPERA_SEGUNDOS,
                )
            else:
                procesador = ProcesadorEventosParametricos(*argumentos)
        except ValueError as exc:
            logger.error("eventos_parametricos_sin_configurar error=%s", exc)
        else:
            tareas.append(asyncio.create_task(procesador.ejecutar()))
    try:
        yield
    finally:
        for tarea in tareas:
            tarea.cancel()
            try:
                await tarea
            except asyncio.CancelledError:
                pass
        for recurso in cierres:
            await recurso.aclose()
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
app.include_router(operador.router, prefix=settings.API_PREFIX)
app.include_router(evidencias.router, prefix=settings.API_PREFIX)
app.include_router(parametricos.router, prefix=settings.API_PREFIX)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Solventa Insurance Claims Service"}
