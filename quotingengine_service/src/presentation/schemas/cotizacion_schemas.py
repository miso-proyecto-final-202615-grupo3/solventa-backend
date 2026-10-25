import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SolicitudCotizacionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cliente_id: uuid.UUID
    producto_codigo: str = Field(min_length=1, max_length=50)
    parametros: dict[str, Any] = Field(default_factory=dict)
    socio_id: uuid.UUID | None = None


class AjusteResponse(BaseModel):
    concepto: str
    tipo: str
    valor: Decimal
    motivo: str


class ImpuestoResponse(BaseModel):
    concepto: str
    tasa: Decimal
    valor: Decimal


class CoberturaCotizadaResponse(BaseModel):
    cobertura_id: uuid.UUID
    codigo: str
    nombre: str
    prima: Decimal
    limite_asegurado: Decimal
    deducible: Decimal


class CotizacionResponse(BaseModel):
    cotizacion_id: uuid.UUID
    cliente_id: uuid.UUID
    producto_codigo: str
    estado: str
    moneda: str
    prima_base: Decimal
    ajustes: list[AjusteResponse]
    impuestos: list[ImpuestoResponse]
    prima_total: Decimal
    degradada: bool
    motivos_degradacion: list[str]
    coberturas: list[CoberturaCotizadaResponse]
    expira_en: datetime
    creada_en: datetime | None


def cotizacion_response(detalle: Any) -> CotizacionResponse:
    c = detalle.cotizacion
    r = detalle.resultado
    degradaciones = r.get("degradaciones", [])
    return CotizacionResponse(
        cotizacion_id=c.cotizacion_id,
        cliente_id=c.cliente_id,
        producto_codigo=detalle.producto_codigo,
        estado=c.estado.value,
        moneda=c.moneda,
        prima_base=r.get("prima_base", "0"),
        ajustes=r.get("ajustes", []),
        impuestos=r.get("impuestos", []),
        prima_total=c.prima_total,
        degradada=bool(degradaciones),
        motivos_degradacion=degradaciones,
        coberturas=[
            CoberturaCotizadaResponse(
                cobertura_id=d.cobertura_id,
                codigo=cob.codigo,
                nombre=cob.nombre,
                prima=d.prima,
                limite_asegurado=d.limite_asegurado,
                deducible=d.deducible,
            )
            for d, cob in detalle.coberturas
        ],
        expira_en=c.expira_en,
        creada_en=c.creada_en,
    )
