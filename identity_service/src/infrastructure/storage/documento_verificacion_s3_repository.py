import logging
import uuid

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from starlette.concurrency import run_in_threadpool

from src.core.config import settings
from src.domain.verificaciones_kyc_aml.entities import (
    ArchivoDocumento,
    RutasDocumentos,
    construir_ruta,
)
from src.domain.verificaciones_kyc_aml.repositories import (
    AlmacenamientoDocumentosError,
    DocumentoVerificacionRepository,
)

logger = logging.getLogger(__name__)


class S3DocumentoVerificacionRepository(DocumentoVerificacionRepository):
    """Guarda las fotos en un bucket S3 privado.

    Igual que Cognito, autentica con la cadena de credenciales por defecto de
    boto3: Pod Identity en EKS o AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY.
    """

    def __init__(
        self,
        bucket: str | None = None,
        region_name: str | None = None,
        kms_key_id: str | None = None,
        client=None,
    ) -> None:
        self.bucket = bucket or settings.S3_BUCKET_NAME
        self.kms_key_id = kms_key_id if kms_key_id is not None else settings.KMS_KEY_ARN
        self._client = client or boto3.client(
            "s3", region_name=region_name or settings.AWS_REGION
        )

    async def guardar(
        self,
        cliente_id: uuid.UUID,
        verificacion_id: uuid.UUID,
        frontal: ArchivoDocumento,
        reverso: ArchivoDocumento,
    ) -> RutasDocumentos:
        if not self.bucket:
            raise AlmacenamientoDocumentosError("El bucket S3 no está configurado.")
        claves = {
            lado: construir_ruta(
                cliente_id, verificacion_id, f"documento-{lado}.{archivo.extension}"
            )
            for lado, archivo in (("frontal", frontal), ("reverso", reverso))
        }
        try:
            for lado, archivo in (("frontal", frontal), ("reverso", reverso)):
                await run_in_threadpool(self._subir, claves[lado], archivo)
        except (ClientError, BotoCoreError) as exc:
            logger.exception("No se pudieron almacenar los documentos en S3.")
            raise AlmacenamientoDocumentosError(str(exc)) from exc
        return RutasDocumentos(
            frontal=f"s3://{self.bucket}/{claves['frontal']}",
            reverso=f"s3://{self.bucket}/{claves['reverso']}",
        )

    def _subir(self, clave: str, archivo: ArchivoDocumento) -> None:
        extra = {"ServerSideEncryption": "AES256"}
        if self.kms_key_id:
            extra = {"ServerSideEncryption": "aws:kms", "SSEKMSKeyId": self.kms_key_id}
        self._client.put_object(
            Bucket=self.bucket,
            Key=clave,
            Body=archivo.contenido,
            ContentType=archivo.content_type,
            **extra,
        )
