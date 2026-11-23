"""Adaptadores de `SolicitudesPago` (HU4.2.3, supuesto P7).

- `registro`: deja la solicitud en el log (local y CI). Pagos aún no consume la solicitud.
- `sqs`: publica la solicitud en `PAGO_INDEMNIZACION_QUEUE_URL` (mismo patrón que `payments_service`).
  Credenciales por la cadena de boto3 (Pod Identity en EKS); en local, LocalStack con `SQS_ENDPOINT_URL`.
"""
import asyncio
import json
import logging

import boto3

logger = logging.getLogger(__name__)


class RegistroSolicitudesPago:
    async def solicitar(self, solicitud: dict, correlation_id: str) -> None:
        logger.info(
            "pago_indemnizacion_solicitado numero=%s monto=%s moneda=%s clave=%s correlation_id=%s",
            solicitud.get("numero"), solicitud.get("monto"), solicitud.get("moneda"),
            solicitud.get("clave_idempotencia"), correlation_id,
        )

    async def aclose(self) -> None:
        return None


class SqsSolicitudesPago:
    def __init__(self, queue_url: str, region_name: str, endpoint_url: str = "", client=None) -> None:
        if not queue_url:
            raise ValueError("Falta PAGO_INDEMNIZACION_QUEUE_URL para SOLICITUDES_PAGO=sqs.")
        self.queue_url = queue_url
        self._client = client or boto3.client("sqs", region_name=region_name, endpoint_url=endpoint_url or None)

    async def solicitar(self, solicitud: dict, correlation_id: str) -> None:
        await asyncio.to_thread(self._enviar, solicitud, correlation_id)
        logger.info("pago_indemnizacion_publicado numero=%s correlation_id=%s", solicitud.get("numero"), correlation_id)

    def _enviar(self, solicitud: dict, correlation_id: str) -> None:
        self._client.send_message(
            QueueUrl=self.queue_url,
            MessageBody=json.dumps(solicitud, separators=(",", ":")),
            MessageAttributes={
                "tipo": {"DataType": "String", "StringValue": solicitud.get("tipo", "PAGO_INDEMNIZACION_SOLICITADO")},
                "correlation_id": {"DataType": "String", "StringValue": correlation_id},
            },
        )

    async def aclose(self) -> None:
        return None


def crear_solicitudes_pago(settings):
    tipo = settings.SOLICITUDES_PAGO.strip().lower()
    if tipo == "registro":
        return RegistroSolicitudesPago()
    if tipo == "sqs":
        return SqsSolicitudesPago(settings.PAGO_INDEMNIZACION_QUEUE_URL, settings.AWS_REGION, settings.SQS_ENDPOINT_URL)
    raise ValueError(f"SOLICITUDES_PAGO desconocido: {settings.SOLICITUDES_PAGO}")
