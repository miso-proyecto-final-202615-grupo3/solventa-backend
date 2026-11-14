import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from src.domain.siniestros.enums import CanalReporte


@dataclass
class EventoExterno:
    event_id: str
    fuente: str
    tipo: str
    checksum: str
    ocurrido_en: datetime
    recibido_en: datetime
    payload_referencia: str
    evento_externo_id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class ActivacionParametrica:
    evento_externo_id: uuid.UUID
    cobertura_id: uuid.UUID
    regla_aplicada: str
    estado: str
    clave_idempotencia: str
    activada_en: datetime
    activacion_id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class ActivacionPoliza:
    activacion_id: uuid.UUID
    poliza_id: uuid.UUID
    estado: str
    clave_idempotencia: str
    identificada_en: datetime
    activacion_poliza_id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class Siniestro:
    poliza_id: uuid.UUID
    tipo: str
    estado: str
    clave_idempotencia: str
    ocurrido_en: datetime
    reportado_en: datetime
    activacion_id: uuid.UUID | None = None
    evidencia_referencia: dict | list | None = None
    # Siniestro asistido reportado por el cliente (HU4.1.1).
    cliente_id: uuid.UUID | None = None
    numero: str | None = None
    canal: str = CanalReporte.PARAMETRICO.value
    descripcion: str | None = None
    poliza_numero: str | None = None
    producto_codigo: str | None = None
    huella_solicitud: str | None = None
    siniestro_id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class Indemnizacion:
    siniestro_id: uuid.UUID
    monto_aprobado: Decimal
    moneda: str
    estado: str
    aprobada_en: datetime | None = None
    indemnizacion_id: uuid.UUID = field(default_factory=uuid.uuid4)
