import logging

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from starlette.concurrency import run_in_threadpool

from src.core.config import settings
from src.domain.certificados.repositories import (
    AlmacenamientoCertificadoError,
    AlmacenamientoCertificadoRepository,
    CertificadoNoEncontradoError,
)

logger = logging.getLogger(__name__)

_CODIGOS_NO_ENCONTRADO = {"NoSuchKey", "404", "NotFound"}


class S3AlmacenamientoCertificadoRepository(AlmacenamientoCertificadoRepository):
    """Guarda los certificados en un bucket S3 privado con SSE-S3 (AES256).

    Autentica con la cadena de credenciales por defecto de boto3: Pod Identity en EKS o
    AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY.
    """

    def __init__(
        self,
        bucket: str | None = None,
        region_name: str | None = None,
        client=None,
    ) -> None:
        self.bucket = bucket or settings.S3_BUCKET_NAME
        self._client = client or boto3.client(
            "s3", region_name=region_name or settings.AWS_REGION
        )

    async def guardar(self, ruta: str, contenido: bytes) -> None:
        self._exigir_bucket()
        try:
            await run_in_threadpool(self._subir, ruta, contenido)
        except (ClientError, BotoCoreError) as exc:
            logger.exception("No se pudo almacenar el certificado en S3.")
            raise AlmacenamientoCertificadoError(str(exc)) from exc

    async def leer(self, ruta: str) -> bytes:
        self._exigir_bucket()
        try:
            return await run_in_threadpool(self._descargar, ruta)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in _CODIGOS_NO_ENCONTRADO:
                raise CertificadoNoEncontradoError(ruta) from exc
            logger.exception("No se pudo leer el certificado de S3.")
            raise AlmacenamientoCertificadoError(str(exc)) from exc
        except BotoCoreError as exc:
            logger.exception("No se pudo leer el certificado de S3.")
            raise AlmacenamientoCertificadoError(str(exc)) from exc

    async def eliminar(self, ruta: str) -> None:
        try:
            await run_in_threadpool(self._client.delete_object, Bucket=self.bucket, Key=ruta)
        except (ClientError, BotoCoreError):
            logger.warning("No se pudo eliminar el certificado huérfano de S3.", exc_info=True)

    def _exigir_bucket(self) -> None:
        if not self.bucket:
            raise AlmacenamientoCertificadoError("El bucket S3 no está configurado.")

    def _subir(self, ruta: str, contenido: bytes) -> None:
        self._client.put_object(
            Bucket=self.bucket,
            Key=ruta,
            Body=contenido,
            ContentType="application/pdf",
            ServerSideEncryption="AES256",
        )

    def _descargar(self, ruta: str) -> bytes:
        return self._client.get_object(Bucket=self.bucket, Key=ruta)["Body"].read()
