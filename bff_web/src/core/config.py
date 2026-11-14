from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Solventa BFF Web"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    API_PREFIX: str = "/api/v1/bff-web"
    IDENTITY_SERVICE_URL: str = "http://localhost:8002"
    QUOTINGENGINE_SERVICE_URL: str = "http://localhost:8003"
    INSURANCEPOLICIES_SERVICE_URL: str = "http://localhost:8004"
    PAYMENTS_SERVICE_URL: str = "http://localhost:8006"
    FIRMA_MAX_REQUEST_BYTES: int = Field(default=2 * 1024 * 1024, gt=0)
    TRAZABILIDAD_INTERNAL_TOKEN: str = ""
    COGNITO_REGION: str = ""
    COGNITO_USER_POOL_ID: str = ""
    COGNITO_CLIENT_ID: str = ""
    COGNITO_AUDITOR_GROUP: str = "Auditor"
    COGNITO_JWKS_TTL_SECONDS: int = 3600
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4317"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
