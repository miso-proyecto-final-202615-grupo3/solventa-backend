from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Solventa Quoting Engine Service"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    API_PREFIX: str = "/api/v1/quotingengine-service"
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/quotingengine_db"
    )
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4317"
    REDIS_ENDPOINT: str = "redis://localhost:6379/0"
    REDIS_AUTH_TOKEN: str = ""
    RATING_CACHE_TTL_SECONDS: int = 300
    COTIZACION_VIGENCIA_DIAS: int = 15
    SEED_ON_STARTUP: bool = True
    IDENTITY_GRPC_ADDRESS: str = "localhost:50051"
    # ESC-001: el adaptador limita la espera a 120 ms
    IDENTITY_GRPC_TIMEOUT_SECONDS: float = 0.12
    IDENTITY_GRPC_MAX_CONCURRENCY: int = 50
    IDENTITY_CB_FAILURE_THRESHOLD: int = 5
    IDENTITY_CB_RECOVERY_SECONDS: float = 15.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
