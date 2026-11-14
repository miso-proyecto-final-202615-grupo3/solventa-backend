"""Puerto hacia MS Pólizas: Siniestros no conoce su API (táctica: encapsular)."""
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass(frozen=True)
class PolizaResumen:
    poliza_id: uuid.UUID
    cliente_id: uuid.UUID
    numero: str
    estado: str
    producto_codigo: str
    producto_nombre: str
    vigencia_desde: date
    vigencia_hasta: date


class PolizasNoDisponibles(Exception):
    """MS Pólizas no respondió a tiempo, falló o devolvió algo que no cumple el contrato."""


class PolizasPort(Protocol):
    async def listar_por_cliente(self, cliente_id: uuid.UUID, correlation_id: str) -> list[PolizaResumen]: ...

    async def obtener(self, poliza_id: uuid.UUID, cliente_id: uuid.UUID, correlation_id: str) -> PolizaResumen | None:
        """La póliza si existe **y es del cliente**; `None` en cualquier otro caso (404 uniforme)."""
        ...
