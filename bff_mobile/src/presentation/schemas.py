import uuid
from datetime import date, datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    """Credenciales de la cuenta creada en el canal web."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    correo: EmailStr
    password: str = Field(min_length=1, max_length=128)
    installation_id: uuid.UUID | None = None


class RefreshSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    refresh_token: str = Field(min_length=1, max_length=4096)


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


# --- HU4.1.1 · Registrar un siniestro (contrato canónico: docs/planning/HU4.1.1-plan-tecnico.md §3) ---

class EvidenciaReglas(BaseModel):
    fotos_max: int = Field(ge=0)
    videos_max: int = Field(ge=0)


class TipoSiniestro(BaseModel):
    codigo: str
    nombre: str
    evidencia: EvidenciaReglas


class ProductoPoliza(BaseModel):
    codigo: str
    nombre: str


class PolizaElegible(BaseModel):
    poliza_id: uuid.UUID
    numero: str
    producto: ProductoPoliza
    vigencia_desde: date
    vigencia_hasta: date
    tipos_siniestro: list[TipoSiniestro] = Field(min_length=1)


class PolizasElegiblesResponse(BaseModel):
    polizas: list[PolizaElegible]


class ReportarSiniestroRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    poliza_id: uuid.UUID
    tipo: str = Field(pattern=r"^[A-Z_]{3,40}$")
    descripcion: str = Field(min_length=10, max_length=500)
    ocurrido_en: AwareDatetime

    @field_validator("descripcion", mode="before")
    @classmethod
    def _sin_espacios_extremos(cls, valor):
        return valor.strip() if isinstance(valor, str) else valor


class SiniestroResponse(BaseModel):
    siniestro_id: uuid.UUID
    numero: str
    estado: str
    poliza_id: uuid.UUID
    poliza_numero: str | None
    tipo: str
    ocurrido_en: datetime
    reportado_en: datetime
