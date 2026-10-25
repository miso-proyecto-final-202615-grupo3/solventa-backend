from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Solventa Motor de Cotización"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    API_PREFIX: str = "/api/v1/motor-cotizacion"
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4317"
    IDENTITY_GRPC_TARGET: str = "localhost:50051"
    IDENTITY_GRPC_TIMEOUT_SECONDS: float = Field(default=0.3, gt=0, le=0.7)
    OPEN_DATA_URL: str = ""
    OPEN_DATA_TIMEOUT_SECONDS: float = Field(default=0.25, gt=0, le=0.7)
    OPEN_DATA_CACHE_TTL_SECONDS: int = 300
    REDIS_ENDPOINT: str = "redis://localhost:6379/0"
    REDIS_AUTH_TOKEN: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
