"""Evidencias en S3 (o MinIO en local) con `POST` prefirmado (decisiones E1, E2 y E4 de HU4.1.2).

La política firmada fija la llave exacta, el `Content-Type`, el rango de tamaño y el cifrado: S3
rechaza cualquier subida que no cumpla. `boto3` es síncrono, por eso todo corre en `asyncio.to_thread`.
Nunca registra la URL firmada ni los campos de la política.
"""
import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from src.application.ports.almacen_evidencias import AlmacenNoDisponible, CargaPrefirmada, MetadatosObjeto

logger = logging.getLogger(__name__)

SSE_KMS = "aws:kms"
_NO_EXISTE = {"404", "NoSuchKey", "NotFound"}


class S3AlmacenEvidencias:
    def __init__(
        self,
        bucket: str,
        sse: str = SSE_KMS,
        kms_key_id: str | None = None,
        cliente_interno: BaseClient | None = None,
        cliente_firma: BaseClient | None = None,
        reloj=lambda: datetime.now(UTC),
    ) -> None:
        self.bucket = bucket
        self.sse = sse
        self.kms_key_id = kms_key_id or None
        self._interno = cliente_interno
        self._firma = cliente_firma or cliente_interno
        self._reloj = reloj

    @classmethod
    def desde_configuracion(
        cls,
        bucket: str,
        region: str,
        sse: str,
        kms_key_id: str | None,
        endpoint_url: str | None,
        public_endpoint_url: str | None,
    ) -> "S3AlmacenEvidencias":
        # Un AWS_PROFILE vacío (compose lo vacía para este servicio) significa "sin perfil", no un perfil "".
        if os.environ.get("AWS_PROFILE") == "":
            os.environ.pop("AWS_PROFILE")
        config = Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"},
                        s3={"addressing_style": "path" if endpoint_url else "auto"})
        try:
            interno = boto3.client("s3", region_name=region, endpoint_url=endpoint_url or None, config=config)
            # La URL que recibe la app debe ser alcanzable desde el teléfono (en local, MinIO por 10.0.2.2).
            firma = (
                boto3.client("s3", region_name=region, endpoint_url=public_endpoint_url, config=config)
                if public_endpoint_url
                else interno
            )
        except BotoCoreError as exc:  # p. ej. un AWS_PROFILE que no existe
            logger.error("almacen_evidencias_configuracion_invalida error=%s", type(exc).__name__)
            raise AlmacenNoDisponible() from exc
        return cls(bucket, sse, kms_key_id, interno, firma)

    async def generar_carga(self, clave: str, content_type: str, tamano_max: int, ttl: timedelta) -> CargaPrefirmada:
        campos = {"Content-Type": content_type, "x-amz-server-side-encryption": self.sse}
        condiciones: list = [
            {"key": clave},
            {"Content-Type": content_type},
            ["content-length-range", 1, tamano_max],
            {"x-amz-server-side-encryption": self.sse},
        ]
        if self.sse == SSE_KMS and self.kms_key_id:
            campos["x-amz-server-side-encryption-aws-kms-key-id"] = self.kms_key_id
            condiciones.append({"x-amz-server-side-encryption-aws-kms-key-id": self.kms_key_id})
        expira_en = self._reloj() + ttl
        firmado = await self._llamar(
            self._firma.generate_presigned_post,
            Bucket=self.bucket, Key=clave, Fields=campos, Conditions=condiciones, ExpiresIn=int(ttl.total_seconds()),
        )
        return CargaPrefirmada(url=firmado["url"], campos=dict(firmado["fields"]), expira_en=expira_en)

    async def metadatos(self, clave: str) -> MetadatosObjeto | None:
        try:
            respuesta = await self._llamar(self._interno.head_object, Bucket=self.bucket, Key=clave, sin_404=True)
        except _ObjetoNoExiste:
            return None
        return MetadatosObjeto(
            tamano=int(respuesta["ContentLength"]),
            content_type=respuesta.get("ContentType", ""),
            cifrado=respuesta.get("ServerSideEncryption"),
        )

    async def leer_inicio(self, clave: str, n_bytes: int) -> bytes:
        respuesta = await self._llamar(self._interno.get_object, Bucket=self.bucket, Key=clave, Range=f"bytes=0-{n_bytes - 1}")
        return await asyncio.to_thread(respuesta["Body"].read)

    async def eliminar(self, clave: str) -> None:
        await self._llamar(self._interno.delete_object, Bucket=self.bucket, Key=clave)

    async def _llamar(self, metodo, sin_404: bool = False, **kwargs):
        try:
            return await asyncio.to_thread(metodo, **kwargs)
        except ClientError as exc:
            codigo = str(exc.response.get("Error", {}).get("Code", ""))
            if sin_404 and codigo in _NO_EXISTE:
                raise _ObjetoNoExiste() from exc
            logger.warning("almacen_evidencias_error operacion=%s codigo=%s", metodo.__name__, codigo)
            raise AlmacenNoDisponible() from exc
        except BotoCoreError as exc:
            logger.warning("almacen_evidencias_error operacion=%s error=%s", metodo.__name__, type(exc).__name__)
            raise AlmacenNoDisponible() from exc


class _ObjetoNoExiste(Exception):
    pass
