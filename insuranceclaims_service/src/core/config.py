from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Solventa Insurance Claims Service"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    API_PREFIX: str = "/api/v1/insuranceclaims-service"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/insuranceclaims_db"
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4317"
    SEED_ON_STARTUP: bool = True
    # MS Pólizas (HU4.1.1 + #265). `memoria` usa pólizas ficticias (solo demos sin MS Pólizas).
    POLIZAS_ADAPTER: str = "http"
    INSURANCEPOLICIES_SERVICE_URL: str = "http://localhost:8004"
    # Catálogo de productos (código y nombre a partir del producto_id de la póliza).
    QUOTINGENGINE_SERVICE_URL: str = "http://localhost:8003"
    POLIZAS_TIMEOUT_SECONDS: float = 3.0
    POLIZAS_SEMILLA_PATH: str = ""
    # MS Pólizas deja la póliza en EMITIDA al emitirla; la vigencia se valida por fechas.
    ESTADOS_POLIZA_ELEGIBLES: str = "EMITIDA,VIGENTE"
    # Evidencias (HU4.1.2). `memoria` solo para pruebas. En AWS las credenciales llegan por EKS Pod Identity.
    ALMACEN_EVIDENCIAS: str = "s3"
    S3_BUCKET_NAME: str = ""
    KMS_KEY_ARN: str = ""
    EVIDENCIAS_PREFIX: str = "siniestros/"
    EVIDENCIAS_SSE: str = "aws:kms"
    AWS_REGION: str = "us-east-1"
    S3_ENDPOINT_URL: str = ""
    S3_PUBLIC_ENDPOINT_URL: str = ""
    FOTO_MAX_MB: int = 5
    VIDEO_MAX_MB: int = 50
    # HU4.2.1: vigencia de la URL de lectura de una evidencia.
    EVIDENCIAS_DESCARGA_TTL_SECONDS: int = 300

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
