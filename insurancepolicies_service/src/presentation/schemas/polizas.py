from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PolizaCoberturaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cobertura_id: UUID
    limite_asegurado: Decimal
    deducible: Decimal
    prima: Decimal


class PolizaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    poliza_id: UUID
    cliente_id: UUID
    cotizacion_id: UUID
    producto_id: UUID
    numero: str
    estado: str
    vigencia_desde: datetime
    vigencia_hasta: datetime
    emitida_en: datetime | None
    ramo: str
    prima_total: Decimal
    coberturas: list[PolizaCoberturaResponse]
    documento_url: str | None = None
