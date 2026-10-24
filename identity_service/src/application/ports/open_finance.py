from abc import ABC, abstractmethod
import uuid

from src.domain.perfilamiento.entities import PerfilOpenFinance


class OpenFinanceProvider(ABC):
    @abstractmethod
    async def obtener_perfil_financiero(
        self, cliente_id: uuid.UUID
    ) -> PerfilOpenFinance:
        raise NotImplementedError
