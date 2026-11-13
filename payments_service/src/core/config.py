from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Solventa Payments Service"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    API_PREFIX: str = "/api/v1/payments-service"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/payments_db"
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4317"

    QUOTINGENGINE_SERVICE_URL: str = "http://localhost:8003"
    INSURANCEPOLICIES_SERVICE_URL: str = "http://localhost:8004"
    SERVICES_TIMEOUT_SECONDS: float = 3.0
    # La firma digital (HU1.3.5) debe existir antes de cobrar la prima.
    REQUIRE_FIRMA_DIGITAL: bool = True

    PAYMENT_PROVIDER_URL: str = "http://localhost:8204"
    PAYMENT_PROVIDER_NAME: str = "mock_paymentprovider"
    PAYMENT_PROVIDER_TIMEOUT_SECONDS: float = 10.0
    # Un pago PENDIENTE más antiguo que esto se considera abandonado y puede reintentarse.
    PAGO_PENDIENTE_TTL_SECONDS: int = 120

    # Bus de eventos (SQS). Sin cola configurada los eventos quedan en el outbox sin publicarse.
    AWS_REGION: str = "us-east-1"
    PAGO_APROBADO_QUEUE_URL: str = ""
    # Solo para LocalStack en desarrollo; vacío usa el endpoint real de AWS.
    SQS_ENDPOINT_URL: str = ""
    OUTBOX_POLL_SECONDS: float = 10.0
    OUTBOX_BATCH_SIZE: int = 10

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
