from typing import Literal

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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
