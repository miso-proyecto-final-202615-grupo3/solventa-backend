import uuid
from abc import ABC, abstractmethod


class CotizacionNoEncontradaError(Exception):
    pass


class CotizacionNoPerteneceAlClienteError(Exception):
    pass


class CotizacionNoDisponibleError(Exception):
    pass


class CotizacionKycGateway(ABC):
    @abstractmethod
    async def validar_cliente(
        self, cotizacion_id: uuid.UUID, cliente_id: uuid.UUID, correlation_id: str
    ) -> None:
        raise NotImplementedError
