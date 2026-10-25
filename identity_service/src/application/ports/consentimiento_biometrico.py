from abc import ABC, abstractmethod
from uuid import UUID


class ConsentimientoBiometricoPort(ABC):
    @abstractmethod
    async def otorgado(self, cliente_id: UUID) -> bool:
        """Indica si el cliente autorizó el tratamiento biométrico."""

        raise NotImplementedError
