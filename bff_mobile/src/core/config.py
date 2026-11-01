from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Solventa BFF Mobile"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    API_PREFIX: str = "/api/v1/bff-mobile"
    IDENTITY_SERVICE_URL: str = "http://localhost:8000"
    IDENTITY_TIMEOUT_SECONDS: float = 5.0
    ALLOW_DEMO_ACTIVATION_WITHOUT_JWT: bool = False
    ACTIVATION_TIMEOUT_SECONDS: float = 20.0
    COGNITO_REGION: str = ""
    COGNITO_USER_POOL_ID: str = ""
    COGNITO_CLIENT_ID: str = ""
    COGNITO_JWKS_TTL_SECONDS: int = 3600
    QUOTINGENGINE_SERVICE_URL: str = "http://localhost:8000"
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4317"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
