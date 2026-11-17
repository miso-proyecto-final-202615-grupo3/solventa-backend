from pydantic import BaseModel, ConfigDict, EmailStr, Field


class PasswordVerify(BaseModel):
    """Credenciales para autenticar a un cliente."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    correo: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshSessionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    refresh_token: str = Field(min_length=1, max_length=4096)


class SolicitudRecuperacionClaveRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    correo: EmailStr


class ConfirmacionRecuperacionClaveRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    correo: EmailStr
    codigo: str = Field(min_length=4, max_length=32)
    nueva_clave: str = Field(min_length=8, max_length=128)


class MensajeResponse(BaseModel):
    mensaje: str


class AutenticarResponse(BaseModel):
    """Tokens emitidos tras una autenticación exitosa."""

    access_token: str
    id_token: str
    refresh_token: str | None = None
    expires_in: int | None = None
    token_type: str = "Bearer"
