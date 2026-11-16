import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class Titular:
    nombre_completo: str
    tipo_documento: str
    numero_identificacion: str


class TitularGateway(ABC):
    @abstractmethod
    async def obtener(self, cliente_id: uuid.UUID, correlation_id: str) -> Titular:
        """Lanza ServicioNoDisponibleError si el cliente no se pudo consultar."""
        raise NotImplementedError
