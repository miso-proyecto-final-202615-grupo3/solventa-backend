import logging

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from starlette.concurrency import run_in_threadpool

from src.core.config import settings
from src.domain.firmas.entities import ArchivoFirma
from src.domain.firmas.repositories import (
    AlmacenamientoFirmaError,
    AlmacenamientoFirmaRepository,
)

logger = logging.getLogger(__name__)


class S3AlmacenamientoFirmaRepository(AlmacenamientoFirmaRepository):
    """Guarda la firma en un bucket S3 privado con SSE-S3 (AES256).

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

    async def guardar(self, ruta: str, archivo: ArchivoFirma) -> None:
        if not self.bucket:
            raise AlmacenamientoFirmaError("El bucket S3 no está configurado.")
        try:
            await run_in_threadpool(self._subir, ruta, archivo)
        except (ClientError, BotoCoreError) as exc:
            logger.exception("No se pudo almacenar la firma en S3.")
            raise AlmacenamientoFirmaError(str(exc)) from exc

    async def eliminar(self, ruta: str) -> None:
        try:
            await run_in_threadpool(
                self._client.delete_object, Bucket=self.bucket, Key=ruta
            )
        except (ClientError, BotoCoreError):
            logger.warning("No se pudo eliminar la firma huérfana de S3.", exc_info=True)

    def _subir(self, ruta: str, archivo: ArchivoFirma) -> None:
        self._client.put_object(
            Bucket=self.bucket,
            Key=ruta,
            Body=archivo.contenido,
            ContentType=archivo.content_type,
            ServerSideEncryption="AES256",
        )
