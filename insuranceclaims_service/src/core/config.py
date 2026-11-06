from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Solventa Insurance Claims Service"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    API_PREFIX: str = "/api/v1/insuranceclaims-service"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/insuranceclaims_db"
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4317"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
