import asyncio
import functools
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import anyio.to_thread
from botocore.exceptions import BotoCoreError, ClientError

from src.core.config import settings
from src.infrastructure.messaging.sqs_publicador import crear_cliente_sqs

logger = logging.getLogger(__name__)

Manejador = Callable[[dict[str, Any]], Awaitable[None]]


class ConsumidorSqs:
    """Lee una cola SQS con long polling y entrega cada mensaje a su manejador.

    Un mensaje se borra solo si el manejador termina bien. Si falla, queda en la cola: SQS lo
    reentrega tras el tiempo de visibilidad y, superado maxReceiveCount, lo mueve a la DLQ de la
    cola. Por eso los manejadores deben ser idempotentes.
    """

    def __init__(
        self,
        nombre: str,
        queue_url: str,
        manejador: Manejador,
        *,
        endpoint_url: str | None = None,
        region_name: str | None = None,
        client=None,
        espera_segundos: int | None = None,
        max_mensajes: int | None = None,
        visibilidad_segundos: int | None = None,
        pausa_error_segundos: float = 5.0,
    ) -> None:
        self.nombre = nombre
        self.queue_url = queue_url
        self._manejador = manejador
        self._client = client or crear_cliente_sqs(endpoint_url, region_name)
        self.espera_segundos = (
            espera_segundos if espera_segundos is not None else settings.SQS_WAIT_SECONDS
        )
        self.max_mensajes = max_mensajes if max_mensajes is not None else settings.SQS_MAX_MESSAGES
        self.visibilidad_segundos = (
            visibilidad_segundos
            if visibilidad_segundos is not None
            else settings.SQS_VISIBILITY_TIMEOUT_SECONDS
        )
        self.pausa_error_segundos = pausa_error_segundos

    async def _en_hilo(self, funcion, **kwargs):
        # abandon_on_cancel: al apagar no se espera a que termine el long polling en curso.
        return await anyio.to_thread.run_sync(
            functools.partial(funcion, **kwargs), abandon_on_cancel=True
        )

    async def procesar_lote(self) -> int:
        """Una lectura de la cola; devuelve cuántos mensajes se procesaron y borraron."""
        respuesta = await self._en_hilo(
            self._client.receive_message,
            QueueUrl=self.queue_url,
            MaxNumberOfMessages=self.max_mensajes,
            WaitTimeSeconds=self.espera_segundos,
            VisibilityTimeout=self.visibilidad_segundos,
            MessageAttributeNames=["All"],
        )
        procesados = 0
        for mensaje in respuesta.get("Messages", []):
            if await self._procesar(mensaje):
                procesados += 1
        return procesados

    async def _procesar(self, mensaje: dict[str, Any]) -> bool:
        id_mensaje = mensaje.get("MessageId")
        try:
            payload = json.loads(mensaje["Body"])
            await self._manejador(payload)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "El consumidor %s no pudo procesar el mensaje %s; vuelve a la cola.",
                self.nombre,
                id_mensaje,
            )
            return False
        try:
            await self._en_hilo(
                self._client.delete_message,
                QueueUrl=self.queue_url,
                ReceiptHandle=mensaje["ReceiptHandle"],
            )
        except (ClientError, BotoCoreError):
            # El mensaje ya se procesó: si reaparece, el manejador idempotente lo ignora.
            logger.warning("No se pudo borrar el mensaje %s de la cola.", id_mensaje, exc_info=True)
            return False
        return True

    async def ejecutar(self) -> None:
        logger.info("Consumidor %s escuchando %s.", self.nombre, self.queue_url)
        while True:
            try:
                await self.procesar_lote()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Falló la lectura de la cola del consumidor %s.", self.nombre)
                await asyncio.sleep(self.pausa_error_segundos)
