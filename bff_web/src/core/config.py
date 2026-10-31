from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Solventa BFF Web"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    API_PREFIX: str = "/api/v1/bff-web"
    IDENTITY_SERVICE_URL: str = "http://localhost:8000"
    QUOTINGENGINE_SERVICE_URL: str = "http://localhost:8003"
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4317"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
