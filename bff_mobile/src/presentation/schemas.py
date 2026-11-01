import uuid
from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, EmailStr, Field


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
    """Datos del dispositivo; el correo se obtiene exclusivamente del JWT."""

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


class VerificarActivacionResponse(BaseModel):
    resultado: str
    folio: str | None = None
    intento: int
    intentos_restantes: int
    dispositivo_vinculado: bool
    vinculado_en: str | None = None
    motivo: str | None = None


class EstadoConsentimientoBiometricoResponse(BaseModel):
    """Contrato 4.3 (HU3.1.3)."""

    otorgado: bool
    version_vigente: str
    version_aceptada: str | None = None
    decidido_en: datetime | None = None


class RegistrarConsentimientoBiometricoRequest(BaseModel):
    """Decisión del cliente; el correo se obtiene exclusivamente del JWT."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    decision: str = Field(pattern="^(ACEPTADO|RECHAZADO)$")
    version_terminos: str = Field(min_length=1, max_length=40)
    installation_id: uuid.UUID
    decidido_en: AwareDatetime


class RegistrarConsentimientoBiometricoResponse(BaseModel):
    decision: str
    version_terminos: str
    registrado_en: datetime
