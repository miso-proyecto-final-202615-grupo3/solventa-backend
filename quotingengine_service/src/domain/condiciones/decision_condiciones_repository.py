from abc import ABC, abstractmethod
import uuid

from src.domain.condiciones.entities import DecisionCondiciones


class DecisionCondicionesRepository(ABC):
    @abstractmethod
    async def guardar(self, decision: DecisionCondiciones) -> None:
        raise NotImplementedError

    @abstractmethod
    async def obtener_ultima(self, condiciones_id: uuid.UUID) -> DecisionCondiciones | None:
        raise NotImplementedError
