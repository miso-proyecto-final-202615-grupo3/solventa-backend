import json
import logging
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from starlette.concurrency import run_in_threadpool

from src.application.ports.publicador_eventos import PublicacionEventoError, PublicadorEventos
from src.core.config import settings

logger = logging.getLogger(__name__)


def crear_cliente_sqs(endpoint_url: str | None = None, region_name: str | None = None):
    """Cliente SQS con la cadena de credenciales por defecto de boto3.

    En EKS usa Pod Identity; en local, AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY. Solo con
    SQS_ENDPOINT_URL apunta a LocalStack; vacío usa el SQS real de AWS.
    """
    endpoint = endpoint_url if endpoint_url is not None else settings.SQS_ENDPOINT_URL
    return boto3.client(
        "sqs", region_name=region_name or settings.AWS_REGION, endpoint_url=endpoint or None
    )


class SqsPublicadorEventos(PublicadorEventos):
    """Publica los eventos en la cola SQS de PolizaEmitida."""

    def __init__(
        self,
        queue_url: str | None = None,
        endpoint_url: str | None = None,
        region_name: str | None = None,
        client=None,
    ) -> None:
        self.queue_url = queue_url if queue_url is not None else settings.POLIZA_EMITIDA_QUEUE_URL
        self._client = client or crear_cliente_sqs(endpoint_url, region_name)

    async def publicar(self, tipo: str, payload: dict[str, Any]) -> None:
        if not self.queue_url:
            raise PublicacionEventoError("La cola SQS no está configurada.")
        try:
            await run_in_threadpool(self._enviar, tipo, payload)
        except (ClientError, BotoCoreError) as exc:
            raise PublicacionEventoError(f"{type(exc).__name__}: {exc}") from exc

    def _enviar(self, tipo: str, payload: dict[str, Any]) -> None:
        self._client.send_message(
            QueueUrl=self.queue_url,
            MessageBody=json.dumps(payload, separators=(",", ":")),
            MessageAttributes={"tipo": {"DataType": "String", "StringValue": tipo}},
        )
