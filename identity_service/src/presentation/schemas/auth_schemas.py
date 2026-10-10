from pydantic import BaseModel, ConfigDict, EmailStr, Field


class PasswordVerify(BaseModel):
    """Credenciales para autenticar a un cliente."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    correo: EmailStr
    password: str = Field(min_length=1, max_length=128)


class AutenticarResponse(BaseModel):
    """Tokens emitidos tras una autenticación exitosa."""

    access_token: str
    id_token: str
    refresh_token: str | None = None
    expires_in: int | None = None
    token_type: str = "Bearer"
