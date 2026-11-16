import asyncio
import logging
from collections.abc import Awaitable
from contextlib import suppress
from datetime import timedelta
from zoneinfo import ZoneInfo

from src.core.config import settings
from src.core.database import SessionLocal
from src.infrastructure.messaging.outbox_relay import OutboxRelay
from src.infrastructure.messaging.sqs_consumidor import ConsumidorSqs
from src.infrastructure.messaging.sqs_publicador import SqsPublicadorEventos
from src.infrastructure.pdf.generador_certificado import GeneradorCertificadoWeasyPrint
from src.presentation.consumers.handlers import ManejadorPagoAprobado, ManejadorPolizaEmitida
from src.presentation.dependencies import (
    get_almacenamiento_certificado_repository,
    get_almacenamiento_firma_repository,
)

logger = logging.getLogger(__name__)


def crear_procesos() -> dict[str, Awaitable[None]]:
    """Procesos en segundo plano que habilita la configuración; cada uno requiere su cola SQS.

    - pago-aprobado: consume PAGO_APROBADO_QUEUE_URL y emite la póliza.
    - outbox-relay: publica PolizaEmitida en POLIZA_EMITIDA_QUEUE_URL.
    - poliza-emitida: consume POLIZA_EMITIDA_QUEUE_URL y genera el certificado PDF.
    """
    procesos: dict[str, Awaitable[None]] = {}
    if settings.PAGO_APROBADO_QUEUE_URL:
        procesos["pago-aprobado"] = ConsumidorSqs(
            "pago-aprobado",
            settings.PAGO_APROBADO_QUEUE_URL,
            ManejadorPagoAprobado(SessionLocal),
        ).ejecutar()
    else:
        logger.warning("PAGO_APROBADO_QUEUE_URL no está configurada: no se emitirán pólizas.")

    if settings.POLIZA_EMITIDA_QUEUE_URL:
        procesos["outbox-relay"] = OutboxRelay(
            SessionLocal,
            SqsPublicadorEventos(),
            settings.OUTBOX_POLL_SECONDS,
            settings.OUTBOX_BATCH_SIZE,
        ).ejecutar()
        procesos["poliza-emitida"] = ConsumidorSqs(
            "poliza-emitida",
            settings.POLIZA_EMITIDA_QUEUE_URL,
            ManejadorPolizaEmitida(
                SessionLocal,
                get_almacenamiento_firma_repository(),
                get_almacenamiento_certificado_repository(),
                GeneradorCertificadoWeasyPrint(),
                ZoneInfo(settings.CERTIFICADO_ZONA_HORARIA),
                timedelta(seconds=settings.CERTIFICADO_EN_PROCESO_TTL_SECONDS),
            ),
        ).ejecutar()
    else:
        logger.warning(
            "POLIZA_EMITIDA_QUEUE_URL no está configurada: no se publicará PolizaEmitida "
            "ni se generarán certificados."
        )
    return procesos


async def detener_procesos(tareas: list[asyncio.Task]) -> None:
    for tarea in tareas:
        tarea.cancel()
    for tarea in tareas:
        with suppress(asyncio.CancelledError):
            await tarea
