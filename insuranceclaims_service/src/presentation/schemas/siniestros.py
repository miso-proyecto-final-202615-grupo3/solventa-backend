import uuid
from datetime import UTC, date, datetime
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, field_serializer

from src.domain.siniestros.catalogo import TipoSiniestro
from src.domain.siniestros.entities import Siniestro

Descripcion = Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=500)]
CodigoTipo = Annotated[str, StringConstraints(pattern=r"^[A-Z_]{3,40}$")]


class ReportarSiniestroRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    poliza_id: uuid.UUID
    tipo: CodigoTipo
    descripcion: Descripcion
    ocurrido_en: AwareDatetime


def _utc(valor: datetime) -> datetime:
    # SQLite devuelve fechas sin zona; todo se guarda en UTC.
    return valor.replace(tzinfo=UTC) if valor.tzinfo is None else valor.astimezone(UTC)


class SiniestroResponse(BaseModel):
    siniestro_id: uuid.UUID
    numero: str
    estado: str
    poliza_id: uuid.UUID
    poliza_numero: str | None
    tipo: str
    ocurrido_en: datetime
    reportado_en: datetime

    @field_serializer("ocurrido_en", "reportado_en")
    def _serializar_utc(self, valor: datetime) -> str:
        return _utc(valor).isoformat().replace("+00:00", "Z")

    @classmethod
    def desde(cls, siniestro: Siniestro) -> "SiniestroResponse":
        return cls(
            siniestro_id=siniestro.siniestro_id,
            numero=siniestro.numero or "",
            estado=siniestro.estado,
            poliza_id=siniestro.poliza_id,
            poliza_numero=siniestro.poliza_numero,
            tipo=siniestro.tipo,
            ocurrido_en=siniestro.ocurrido_en,
            reportado_en=siniestro.reportado_en,
        )


class EvidenciaReglasResponse(BaseModel):
    fotos_max: int
    videos_max: int


class TipoSiniestroResponse(BaseModel):
    codigo: str
    nombre: str
    evidencia: EvidenciaReglasResponse

    @classmethod
    def desde(cls, tipo: TipoSiniestro) -> "TipoSiniestroResponse":
        return cls(
            codigo=tipo.codigo,
            nombre=tipo.nombre,
            evidencia=EvidenciaReglasResponse(fotos_max=tipo.reglas.fotos_max, videos_max=tipo.reglas.videos_max),
        )


class TipoSiniestroCatalogoResponse(TipoSiniestroResponse):
    producto_codigo: str

    @classmethod
    def desde(cls, tipo: TipoSiniestro) -> "TipoSiniestroCatalogoResponse":
        return cls(producto_codigo=tipo.producto_codigo, **TipoSiniestroResponse.desde(tipo).model_dump())


class TiposSiniestroResponse(BaseModel):
    tipos: list[TipoSiniestroCatalogoResponse]


class ProductoResponse(BaseModel):
    codigo: str
    nombre: str


class PolizaElegibleResponse(BaseModel):
    poliza_id: uuid.UUID
    numero: str
    producto: ProductoResponse
    vigencia_desde: date
    vigencia_hasta: date
    tipos_siniestro: list[TipoSiniestroResponse] = Field(min_length=1)


class PolizasElegiblesResponse(BaseModel):
    polizas: list[PolizaElegibleResponse]


class SiniestrosResponse(BaseModel):
    """`GET /siniestros` (HU4.2.1): página de siniestros del cliente, más reciente primero."""

    siniestros: list[SiniestroResponse]
    pagina: int
    tamano: int
    total: int
