from src.core.config import Settings
from src.infrastructure.storage.memoria import AlmacenEvidenciasEnMemoria
from src.infrastructure.storage.s3_almacen import S3AlmacenEvidencias

_almacen: S3AlmacenEvidencias | AlmacenEvidenciasEnMemoria | None = None


def crear_almacen(settings: Settings) -> S3AlmacenEvidencias | AlmacenEvidenciasEnMemoria:
    """Una instancia por proceso: los clientes de boto3 son reutilizables y seguros entre hilos."""
    global _almacen
    if _almacen is None:
        if settings.ALMACEN_EVIDENCIAS.lower() == "memoria":
            _almacen = AlmacenEvidenciasEnMemoria()
        else:
            _almacen = S3AlmacenEvidencias.desde_configuracion(
                bucket=settings.S3_BUCKET_NAME,
                region=settings.AWS_REGION,
                sse=settings.EVIDENCIAS_SSE,
                kms_key_id=settings.KMS_KEY_ARN or None,
                endpoint_url=settings.S3_ENDPOINT_URL or None,
                public_endpoint_url=settings.S3_PUBLIC_ENDPOINT_URL or None,
            )
    return _almacen
