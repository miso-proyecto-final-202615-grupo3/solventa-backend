import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum


class EstadoProducto(StrEnum):
    ACTIVO = "ACTIVO"
    INACTIVO = "INACTIVO"


class EstadoCobertura(StrEnum):
    ACTIVA = "ACTIVA"
    INACTIVA = "INACTIVA"


@dataclass
class Cobertura:
    producto_id: uuid.UUID
    codigo: str
    nombre: str
    limite_asegurado: Decimal
    deducible: Decimal
    estado: EstadoCobertura = EstadoCobertura.ACTIVA
    cobertura_id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class ProductoSeguro:
    codigo: str
    nombre: str
    ramo: str
    pais: str
    estado: EstadoProducto = EstadoProducto.ACTIVO
    producto_id: uuid.UUID = field(default_factory=uuid.uuid4)
