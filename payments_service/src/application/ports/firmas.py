import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class FirmaPago:
    firma_id: uuid.UUID
    cliente_id: uuid.UUID
    estado: str


class FirmaGateway(ABC):
    @abstractmethod
    async def obtener_vigente(
        self, cotizacion_id: uuid.UUID, correlation_id: str
    ) -> FirmaPago | None:
        """Firma vigente de la cotización, o None si no existe."""
        raise NotImplementedError
