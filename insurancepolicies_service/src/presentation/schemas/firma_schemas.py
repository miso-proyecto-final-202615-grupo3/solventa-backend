import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from src.domain.firmas.entities import EstadoFirma


class FirmaDigitalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    firma_id: uuid.UUID
    cotizacion_id: uuid.UUID
    cliente_id: uuid.UUID
    producto_id: uuid.UUID
    poliza_id: uuid.UUID | None
    estado: EstadoFirma
    proveedor_firma: str
    content_type: str
    tamano_bytes: int
    firma_hash: str
    fingerprint_contrato: str
    capturada_en: datetime
