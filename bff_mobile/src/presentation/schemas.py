import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    """Credenciales de la cuenta creada en el canal web."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    correo: EmailStr
    password: str = Field(min_length=1, max_length=128)
    installation_id: uuid.UUID | None = None


class ClienteMovil(BaseModel):
    id: uuid.UUID
    nombre: str
    estado_kyc: str
    dispositivo_vinculado: bool


class LoginResponse(BaseModel):
    """Sesión del cliente para la app móvil.

    `correo` sale del id_token emitido por Cognito. Los datos del cliente
    (id, nombre, estado KYC, dispositivo vinculado) se agregarán cuando el MS
    Identidad exponga una consulta del cliente autenticado.
    """

    access_token: str
    refresh_token: str | None = None
    expires_in: int | None = None
    token_type: str = "Bearer"
    correo: EmailStr | None = None
    cliente: ClienteMovil | None = None


class IniciarActivacionRequest(BaseModel):
    """Datos del dispositivo; el correo se obtiene del JWT, nunca del body."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    installation_id: uuid.UUID
    plataforma: str = Field(pattern="^(ANDROID|IOS)$")
    modelo: str = Field(min_length=1, max_length=100)
    version_so: str = Field(min_length=1, max_length=20)


class IniciarActivacionResponse(BaseModel):
    dispositivo_vinculado: bool
    sesion_id: str | None = None
    expira_en: str | None = None
    captura: dict | None = None
    intentos_restantes: int | None = None
