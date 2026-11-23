"""Bus de eventos paramétricos en Amazon SQS (HU4.2.3, diseño ASR-ESC-002 / HA8).

- `SqsBusEventosParametricos`: la ingesta publica el evento; si SQS no confirma, la fuente recibe 503 y reintenta.
- `ConsumidorSqsEventosParametricos`: competing consumers con long polling. Por cada mensaje:
  registra el evento en `evento_externo` (idempotencia por `event_id` y traza), lo procesa y **solo entonces**
  borra el mensaje. Un error transitorio no borra el mensaje: SQS lo vuelve a entregar al vencer la
  visibilidad y, tras `maxReceiveCount` recepciones, lo mueve a la DLQ (redrive policy de la cola).
  Un evento que no se puede interpretar se envía directo a la DLQ con su causa.
Credenciales: cadena de boto3 (EKS Pod Identity en AWS); en local, el perfil `SQS_AWS_PROFILE`.
"""
import asyncio
import json
import logging

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy.exc import IntegrityError

from src.application.ports.bus_eventos import BusNoDisponible
from src.application.use_cases.eventos_parametricos_use_cases import (
    ProcesarEventoParametricoUseCase,
    evento_desde_mensaje,
)
from src.domain.siniestros.parametricos import EstadoEvento, EventoNoProcesable
from src.infrastructure.messaging.procesador_eventos_parametricos import ProcesadorEventosParametricos, repositorios

logger = logging.getLogger(__name__)


def crear_cliente_sqs(region_name: str, profile_name: str = "", endpoint_url: str = ""):
    sesion = boto3.Session(profile_name=profile_name or None, region_name=region_name)
    return sesion.client("sqs", endpoint_url=endpoint_url or None)


class SqsBusEventosParametricos:
    def __init__(self, queue_url: str, client) -> None:
        if not queue_url:
            raise ValueError("Falta EVENTOS_PARAMETRICOS_QUEUE_URL para EVENTOS_BUS=sqs.")
        self.queue_url = queue_url
        self._client = client

    async def publicar(self, mensaje: dict, correlation_id: str) -> None:
        try:
            await asyncio.to_thread(
                self._client.send_message,
                QueueUrl=self.queue_url,
                MessageBody=json.dumps(mensaje, separators=(",", ":"), default=str),
                MessageAttributes={
                    "tipo": {"DataType": "String", "StringValue": mensaje.get("tipo", "")},
                    "event_id": {"DataType": "String", "StringValue": mensaje.get("event_id", "")},
                },
            )
        except (ClientError, BotoCoreError) as exc:
            logger.warning("evento_parametrico_no_encolado event_id=%s error=%s", correlation_id, type(exc).__name__)
            raise BusNoDisponible(type(exc).__name__) from exc

    async def aclose(self) -> None:
        return None


class ConsumidorSqsEventosParametricos(ProcesadorEventosParametricos):
    """Reutiliza el caso de uso y el registro de errores del consumidor de Postgres; solo cambia el origen."""

    def __init__(self, *args, client, queue_url: str, dlq_url: str = "", espera_segundos: int = 10, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._client = client
        self._queue_url = queue_url
        self._dlq_url = dlq_url
        self._espera = espera_segundos

    async def procesar_pendientes(self) -> int:
        respuesta = await asyncio.to_thread(
            self._client.receive_message,
            QueueUrl=self._queue_url,
            MaxNumberOfMessages=min(self._tamano_lote, 10),
            WaitTimeSeconds=self._espera,
            AttributeNames=["ApproximateReceiveCount"],
        )
        procesados = 0
        for mensaje in respuesta.get("Messages", []):
            if await self._manejar(mensaje):
                procesados += 1
        return procesados

    async def _borrar(self, mensaje: dict) -> None:
        await asyncio.to_thread(self._client.delete_message, QueueUrl=self._queue_url, ReceiptHandle=mensaje["ReceiptHandle"])

    async def _a_dlq(self, mensaje: dict, causa: str) -> None:
        if self._dlq_url:
            await asyncio.to_thread(
                self._client.send_message, QueueUrl=self._dlq_url, MessageBody=mensaje["Body"],
                MessageAttributes={"causa": {"DataType": "String", "StringValue": causa[:250] or "no procesable"}},
            )
        await self._borrar(mensaje)

    async def _manejar(self, mensaje: dict) -> bool:
        """`True` si el mensaje quedó resuelto (procesado, repetido o descartado) y se borró de la cola."""
        try:
            entrante = evento_desde_mensaje(json.loads(mensaje["Body"]))
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("evento_parametrico_mensaje_invalido error=%s", type(exc).__name__)
            await self._a_dlq(mensaje, f"mensaje inválido: {type(exc).__name__}")
            return True
        async with self._session_factory() as session:
            repos = repositorios(session)
            evento = await repos.eventos.obtener_por_event_id(entrante.event_id)
            if evento is None:
                try:
                    await repos.eventos.guardar(entrante)
                    await session.commit()
                    evento = entrante
                except IntegrityError:  # otro consumidor lo registró al mismo tiempo
                    await session.rollback()
                    evento = await repos.eventos.obtener_por_event_id(entrante.event_id)
            if evento.checksum != entrante.checksum:
                logger.warning("evento_parametrico_en_conflicto event_id=%s", entrante.event_id)
                await self._a_dlq(mensaje, "event_id repetido con otro contenido")
                return True
            if evento.estado != EstadoEvento.RECIBIDO.value:
                logger.info("evento_parametrico_repetido event_id=%s estado=%s", evento.event_id, evento.estado)
                await self._borrar(mensaje)
                return True
            caso = ProcesarEventoParametricoUseCase(session, repos, self._polizas, self._reloj, self._estados)
            try:
                await caso.ejecutar(evento)
            except EventoNoProcesable as exc:
                await session.rollback()
                await self._registrar(evento.evento_externo_id, exc.mensaje, descartar=True)
                await self._a_dlq(mensaje, exc.mensaje)
                return True
            except Exception as exc:  # transitorio: el mensaje vuelve a la cola al vencer su visibilidad
                await session.rollback()
                await self._registrar(evento.evento_externo_id, f"{type(exc).__name__}: {exc}", descartar=False)
                return False
        await self._borrar(mensaje)
        return True

    async def ejecutar(self) -> None:
        logger.info("consumidor_sqs_parametrico_iniciado espera_s=%s", self._espera)
        while True:
            try:
                await self.procesar_pendientes()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("consumidor_sqs_parametrico_error")
                await asyncio.sleep(self._intervalo)


def bus_activo(settings) -> str:
    bus = settings.EVENTOS_BUS.strip().lower()
    if bus not in ("postgres", "sqs"):
        raise ValueError(f"EVENTOS_BUS desconocido: {settings.EVENTOS_BUS}")
    return bus


def crear_bus_eventos(settings) -> SqsBusEventosParametricos | None:
    """`None` con el bus de Postgres (la ingesta guarda directo en `evento_externo`)."""
    if bus_activo(settings) != "sqs":
        return None
    cliente = crear_cliente_sqs(settings.AWS_REGION, settings.SQS_AWS_PROFILE, settings.SQS_ENDPOINT_URL)
    return SqsBusEventosParametricos(settings.EVENTOS_PARAMETRICOS_QUEUE_URL, cliente)
