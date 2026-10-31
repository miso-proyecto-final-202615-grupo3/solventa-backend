from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    LIVENESS_PROVIDER: str = "propio"
    LIVENESS_SESSION_TTL_SECONDS: int = 120
    MAX_FRAME_BYTES: int = 524_288
    ADMIN_TOKEN: str = ""


settings = Settings()
