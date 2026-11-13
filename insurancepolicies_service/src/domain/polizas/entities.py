import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

ESTADO_POLIZA_EMITIDA = "EMITIDA"


class EstadoCertificado(StrEnum):
    PENDIENTE = "PENDIENTE"
    GENERADO = "GENERADO"


@dataclass
class PolizaCobertura:
    poliza_id: uuid.UUID
    cobertura_id: uuid.UUID
    limite_asegurado: Decimal
    deducible: Decimal
    prima: Decimal
    poliza_cobertura_id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class Poliza:
    cliente_id: uuid.UUID
    cotizacion_id: uuid.UUID
    producto_id: uuid.UUID
    numero: str
    estado: str
    vigencia_desde: datetime
    vigencia_hasta: datetime
    emitida_en: datetime | None = None
    poliza_id: uuid.UUID = field(default_factory=uuid.uuid4)
    coberturas: list[PolizaCobertura] = field(default_factory=list)
    ramo: str = "SEGURO"
    titular_nombre: str = ""
    estado_certificado: EstadoCertificado = EstadoCertificado.PENDIENTE
    ruta_certificado: str | None = None

    @property
    def prima_total(self) -> Decimal:
        return sum((c.prima for c in self.coberturas), start=Decimal("0"))


@dataclass
class ContratoPoliza:
    """Instantánea de lo contratado (titular, producto, coberturas, prima y condiciones aceptadas).

    Se guarda al emitir la póliza para que el certificado no dependa de que otros servicios
    estén disponibles —ni sigan igual— cuando se genera.
    """

    poliza_id: uuid.UUID
    datos: dict[str, Any]
