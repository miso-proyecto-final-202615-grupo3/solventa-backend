from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Solventa Insurance Claims Service"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    API_PREFIX: str = "/api/v1/insuranceclaims-service"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/insuranceclaims_db"
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4317"
    SEED_ON_STARTUP: bool = True
    # MS Pólizas (HU4.1.1). `memoria` es la excepción transitoria hasta el endpoint interno de #265.
    POLIZAS_ADAPTER: str = "http"
    INSURANCEPOLICIES_SERVICE_URL: str = "http://localhost:8004"
    POLIZAS_TIMEOUT_SECONDS: float = 3.0
    POLIZAS_SEMILLA_PATH: str = ""
    ESTADOS_POLIZA_ELEGIBLES: str = "VIGENTE"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
