from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Solventa Insurance Policies Service"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    API_PREFIX: str = "/api/v1/insurancepolicies-service"
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/insurancepolicies_db"
    )
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4317"
    AWS_REGION: str = "us-east-1"
    FIRMA_STORAGE: Literal["local", "s3"] = "s3"
    # Bucket S3 privado; las credenciales salen de la cadena por defecto de boto3 (Pod Identity o AWS_*).
    S3_BUCKET_NAME: str = ""
    FIRMA_LOCAL_BASE_DIR: str = "/tmp"
    FIRMA_MAX_BYTES: int = 1024 * 1024
    FIRMA_PROVEEDOR: str = "CANVAS_MANUSCRITA"

    # Servicios que aportan los datos al emitir la póliza.
    QUOTINGENGINE_SERVICE_URL: str = "http://localhost:8003"
    IDENTITY_SERVICE_URL: str = "http://localhost:8002"
    SERVICES_TIMEOUT_SECONDS: float = 3.0

    # Colas SQS. Por defecto apuntan al SQS real de AWS: sin URL el consumidor o el relay
    # correspondiente no se inicia. SQS_ENDPOINT_URL solo se usa para LocalStack en desarrollo.
    PAGO_APROBADO_QUEUE_URL: str = ""
    POLIZA_EMITIDA_QUEUE_URL: str = ""
    SQS_ENDPOINT_URL: str = ""
    SQS_WAIT_SECONDS: int = Field(default=20, ge=0, le=20)
    SQS_MAX_MESSAGES: int = Field(default=5, ge=1, le=10)
    # Debe cubrir lo que tarda un mensaje: SQS lo reentrega si se vence antes de borrarlo.
    SQS_VISIBILITY_TIMEOUT_SECONDS: int = Field(default=120, ge=1)
    OUTBOX_POLL_SECONDS: float = 2.0
    OUTBOX_BATCH_SIZE: int = 10

    # Certificado PDF de la póliza.
    CERTIFICADO_STORAGE: Literal["local", "s3"] = "s3"
    CERTIFICADO_LOCAL_BASE_DIR: str = "/tmp"
    CERTIFICADO_ZONA_HORARIA: str = "America/Bogota"
    # Una generación EN_PROCESO más antigua que esto se considera abandonada.
    CERTIFICADO_EN_PROCESO_TTL_SECONDS: int = 300

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
