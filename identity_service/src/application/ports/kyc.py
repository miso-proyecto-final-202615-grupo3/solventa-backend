from abc import ABC, abstractmethod

from src.domain.clientes.value_objects import EstadoKYC


class KycVerifier(ABC):
    @abstractmethod
    async def verificar(
        self, tipo_documento: str, numero_identificacion: str
    ) -> EstadoKYC:
        raise NotImplementedError