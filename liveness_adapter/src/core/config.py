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
    # Signo del yaw de MediaPipe al girar a la derecha (calibrado en Android con cámara frontal).
    PROPIO_RIGHT_TURN_YAW_SIGN: int = -1
    PROPIO_MIN_DURATION_SECONDS: float = 0.3
    PROPIO_MAX_DURATION_SECONDS: float = 15.0
    DIDIT_ENABLED: bool = False
    DIDIT_BASE_URL: str = "http://mock_kyc:8000"
    DIDIT_API_KEY: str = ""
    DIDIT_WORKFLOW_ID: str = ""
    DIDIT_TIMEOUT_SECONDS: float = 5.0
    DIDIT_MAX_SESIONES_DIA: int = 5
    DIDIT_MAX_SESIONES_MES: int = 100


settings = Settings()
