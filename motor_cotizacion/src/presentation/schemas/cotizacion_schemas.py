from datetime import datetime
from decimal import Decimal
from typing import Literal
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class UbicacionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    municipio: str = Field(min_length=2, max_length=100)
    zona: Literal["URBANA", "RURAL"]
    estrato: int = Field(ge=1, le=6)


class ParametrosCotizacion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    saldo_credito: int = Field(gt=0)
    ubicacion: UbicacionRequest


class CotizarRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    cliente_id: uuid.UUID
    ramo: Literal["VIDA_HIPOTECARIO"]
    consentimiento_version: str = Field(min_length=1, max_length=40)
    parametros: ParametrosCotizacion


class DesgloseCotizacion(BaseModel):
    prima_base: Decimal
    ajustes: Decimal
    prima_neta: Decimal
    impuestos: Decimal

    @field_serializer("prima_base", "ajustes", "prima_neta", "impuestos")
    def serializar_monto(self, valor: Decimal) -> float:
        return float(valor)


class CotizacionResponse(BaseModel):
    cotizacion_id: uuid.UUID
    estado: Literal["COTIZADA"]
    ramo: Literal["VIDA_HIPOTECARIO"]
    moneda: Literal["COP"]
    prima_mensual: Decimal
    desglose: DesgloseCotizacion
    explicacion_ajustes: list[str]
    fuente_perfil: Literal["PROVEEDORES", "CACHE", "FALLBACK", "PARCIAL"]
    vigencia_hasta: datetime

    @field_serializer("prima_mensual")
    def serializar_prima_mensual(self, valor: Decimal) -> float:
        return float(valor)
