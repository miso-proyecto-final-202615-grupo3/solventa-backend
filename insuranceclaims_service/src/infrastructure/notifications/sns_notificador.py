"""Notificaciones push por Amazon SNS Mobile Push con FCM HTTP v1 (HU4.2.2, decisión N1).

Por cada envío: `CreatePlatformEndpoint` (idempotente para el mismo token) → asegurar que el endpoint esté
habilitado y con ese token → `Publish` con un mensaje solo de datos (N5). Nunca registra el token completo.

Clasificación de errores (N8):
- `EndpointDisabled` / `NotFound` al publicar → el token ya no es válido (FCM lo dio de baja) → TOKEN_INVALIDO.
- Cualquier otro error (permisos, red, límites, mensaje) → ERROR_TRANSITORIO: el evento se reintenta y el
  token **no** se borra.
"""
import asyncio
import json
import logging
import re

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from src.application.ports.notificador_push import NotificadorPush, ResultadoEnvio

logger = logging.getLogger(__name__)

# SNS responde así si el token ya tiene un endpoint con otros atributos (p. ej. deshabilitado).
_ENDPOINT_EXISTENTE = re.compile(r"Endpoint (arn:aws:sns:\S+) already exists")
_TOKEN_INVALIDO = {"EndpointDisabled", "NotFound"}


class SnsNotificador(NotificadorPush):
    def __init__(self, platform_application_arn: str, region_name: str, profile_name: str = "", client=None) -> None:
        if not platform_application_arn:
            raise ValueError("SNS_PLATFORM_APPLICATION_ARN es obligatorio cuando NOTIFICADOR_PUSH=sns")
        self._application_arn = platform_application_arn
        if client is not None:
            self._client = client
        elif profile_name:  # solo en local; en AWS las credenciales llegan por EKS Pod Identity
            self._client = boto3.Session(profile_name=profile_name).client("sns", region_name=region_name)
        else:
            self._client = boto3.client("sns", region_name=region_name)

    async def enviar(self, token: str, plataforma: str, datos: dict) -> ResultadoEnvio:
        final = token[-6:]
        if plataforma.upper() != "ANDROID":
            logger.warning("push_plataforma_no_soportada plataforma=%s token_final=%s", plataforma, final)
            return ResultadoEnvio.TOKEN_INVALIDO
        try:
            endpoint_arn = await self._endpoint(token)
            mensaje = {"fcmV1Message": {"message": {
                "data": {clave: str(valor) for clave, valor in datos.items()},
                "android": {"priority": "high"},
            }}}
            await asyncio.to_thread(
                self._client.publish,
                TargetArn=endpoint_arn,
                MessageStructure="json",
                Message=json.dumps({"GCM": json.dumps(mensaje)}),
            )
        except ClientError as exc:
            codigo = exc.response.get("Error", {}).get("Code", "")
            if codigo in _TOKEN_INVALIDO:
                logger.info("push_sns_token_invalido codigo=%s token_final=%s", codigo, final)
                return ResultadoEnvio.TOKEN_INVALIDO
            logger.warning("push_sns_error codigo=%s token_final=%s", codigo, final)
            return ResultadoEnvio.ERROR_TRANSITORIO
        except BotoCoreError as exc:
            logger.warning("push_sns_no_disponible error=%s token_final=%s", type(exc).__name__, final)
            return ResultadoEnvio.ERROR_TRANSITORIO
        logger.info("push_sns_enviado evento_id=%s token_final=%s", datos.get("evento_id"), final)
        return ResultadoEnvio.ENVIADO

    async def _endpoint(self, token: str) -> str:
        """ARN del endpoint del token, habilitado y con ese token (un token renovado vuelve a recibir)."""
        try:
            respuesta = await asyncio.to_thread(
                self._client.create_platform_endpoint, PlatformApplicationArn=self._application_arn, Token=token
            )
            arn = respuesta["EndpointArn"]
        except ClientError as exc:
            coincidencia = _ENDPOINT_EXISTENTE.search(exc.response.get("Error", {}).get("Message", ""))
            if exc.response.get("Error", {}).get("Code") != "InvalidParameter" or coincidencia is None:
                raise
            arn = coincidencia.group(1)
        atributos = (await asyncio.to_thread(self._client.get_endpoint_attributes, EndpointArn=arn))["Attributes"]
        if atributos.get("Enabled", "true").lower() != "true" or atributos.get("Token") != token:
            await asyncio.to_thread(
                self._client.set_endpoint_attributes,
                EndpointArn=arn,
                Attributes={"Token": token, "Enabled": "true"},
            )
        return arn
