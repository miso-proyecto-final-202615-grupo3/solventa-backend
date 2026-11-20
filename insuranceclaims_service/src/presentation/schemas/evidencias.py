import uuid
from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_serializer

from src.domain.siniestros.entities import Siniestro
from src.domain.siniestros.evidencias import EvidenciaSiniestro, OrigenEvidencia, TipoEvidencia
from src.domain.siniestros.ubicacion import FuenteUbicacion
from src.presentation.schemas.siniestros import SiniestroResponse, _utc


def _iso(valor: datetime | None) -> str | None:
    return None if valor is None else _utc(valor).isoformat().replace("+00:00", "Z")


class SolicitudCargaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: TipoEvidencia
    content_type: str = Field(min_length=3, max_length=50)
    tamano_bytes: int = Field(gt=0)
    origen: OrigenEvidencia
    capturada_en: AwareDatetime


class CargaResponse(BaseModel):
    url: str
    campos: dict[str, str]
    expira_en: datetime
    tamano_max_bytes: int

    @field_serializer("expira_en")
    def _serializar(self, valor: datetime) -> str:
        return _iso(valor)


class SolicitudCargaResponse(BaseModel):
    evidencia_id: uuid.UUID
    estado: str
    carga: CargaResponse | None  # null: la evidencia de esa Idempotency-Key ya está CARGADA


class EvidenciaResponse(BaseModel):
    evidencia_id: uuid.UUID
    tipo: str
    estado: str
    tamano_bytes: int | None
    capturada_en: datetime
    cargada_en: datetime | None

    @field_serializer("capturada_en", "cargada_en")
    def _serializar(self, valor: datetime | None) -> str | None:
        return _iso(valor)

    @classmethod
    def desde(cls, evidencia: EvidenciaSiniestro) -> "EvidenciaResponse":
        return cls(
            evidencia_id=evidencia.evidencia_id,
            tipo=evidencia.tipo,
            estado=evidencia.estado,
            tamano_bytes=evidencia.tamano_bytes,
            capturada_en=evidencia.capturada_en,
            cargada_en=evidencia.cargada_en,
        )


class UbicacionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latitud: float = Field(ge=-90, le=90)
    longitud: float = Field(ge=-180, le=180)
    precision_m: float = Field(gt=0, le=5000)
    fuente: FuenteUbicacion
    capturada_en: AwareDatetime


class UbicacionResponse(BaseModel):
    latitud: float
    longitud: float
    precision_m: float
    fuente: FuenteUbicacion
    capturada_en: datetime

    @field_serializer("capturada_en")
    def _serializar(self, valor: datetime) -> str:
        return _iso(valor)

    @classmethod
    def desde(cls, siniestro: Siniestro) -> "UbicacionResponse | None":
        ubicacion = siniestro.ubicacion
        if ubicacion is None:
            return None
        return cls(
            latitud=ubicacion.latitud,
            longitud=ubicacion.longitud,
            precision_m=ubicacion.precision_m,
            fuente=ubicacion.fuente,
            capturada_en=ubicacion.capturada_en,
        )


class RegistrarUbicacionResponse(BaseModel):
    ubicacion: UbicacionResponse
    actualizada_en: datetime

    @field_serializer("actualizada_en")
    def _serializar(self, valor: datetime) -> str:
        return _iso(valor)


class SiniestroDetalleResponse(SiniestroResponse):
    """`GET /siniestros/{id}`: el siniestro de HU4.1.1 con su ubicación y evidencias (HU4.1.2)."""

    ubicacion: UbicacionResponse | None = None
    evidencias: list[EvidenciaResponse] = []

    @classmethod
    def desde_detalle(cls, siniestro: Siniestro, evidencias: list[EvidenciaSiniestro]) -> "SiniestroDetalleResponse":
        return cls(
            **SiniestroResponse.desde(siniestro).model_dump(),
            ubicacion=UbicacionResponse.desde(siniestro),
            evidencias=[EvidenciaResponse.desde(e) for e in evidencias],
        )


class DescargaEvidenciaResponse(BaseModel):
    """`GET …/evidencias/{id}/descarga` (HU4.2.1): URL de lectura temporal. Nunca se registra."""

    evidencia_id: uuid.UUID
    tipo: str
    content_type: str
    tamano_bytes: int | None
    url: str
    expira_en: datetime

    @field_serializer("expira_en")
    def _serializar(self, valor: datetime) -> str:
        return _iso(valor)
