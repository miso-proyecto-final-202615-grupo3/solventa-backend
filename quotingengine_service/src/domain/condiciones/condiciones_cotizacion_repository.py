import uuid
from abc import ABC, abstractmethod

from src.domain.condiciones.entities import CondicionesCotizacion


class CondicionesCotizacionRepository(ABC):
    @abstractmethod
    async def guardar(self, condiciones: CondicionesCotizacion) -> None:
        raise NotImplementedError

    @abstractmethod
    async def obtener_por_cotizacion(
        self, cotizacion_id: uuid.UUID
    ) -> CondicionesCotizacion | None:
        raise NotImplementedError
