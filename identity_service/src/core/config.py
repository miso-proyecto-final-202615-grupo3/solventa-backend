from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Solventa Identity Service"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    API_PREFIX: str = "/api/v1/identity-service"
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/identity_db"
    )
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4317"
    AWS_REGION: str = "us-east-1"
    COGNITO_USER_POOL_ID: str = ""
    COGNITO_CLIENT_ID: str = ""
    COGNITO_ENABLED: bool = False
    CONSENT_TERMS_VERSION: str = "1.0"
    CONSENT_CACHE_TTL_SECONDS: int = 300
    REDIS_ENDPOINT: str = "redis://localhost:6379/0"
    REDIS_AUTH_TOKEN: str = ""
    KYC_SERVICE_URL: str = "http://localhost:8202"
    KYC_TIMEOUT_SECONDS: float = 0.7
    GRPC_ENABLED: bool = False
    GRPC_PORT: int = 50051
    OPEN_FINANCE_URL: str = ""
    OPEN_FINANCE_TIMEOUT_SECONDS: float = Field(default=0.2, gt=0, le=0.7)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
