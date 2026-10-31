from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    LIVENESS_PROVIDER: str = "propio"
    LIVENESS_SESSION_TTL_SECONDS: int = 120
    MAX_FRAME_BYTES: int = 524_288
    REDIS_ENDPOINT: str = "redis://localhost:6379/0"
    REDIS_AUTH_TOKEN: str = ""
    ADMIN_TOKEN: str = ""
    PROPIO_MODEL_PATH: str = "/app/models/face_landmarker.task"
    PROPIO_MIN_FACE_WIDTH_RATIO: float = 0.20
    PROPIO_MAX_INTEROCULAR_VARIATION: float = 0.25
    PROPIO_MIN_DURATION_SECONDS: float = 0.3
    PROPIO_MAX_DURATION_SECONDS: float = 15.0


settings = Settings()
