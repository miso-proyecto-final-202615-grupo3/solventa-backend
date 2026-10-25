import uuid
from abc import ABC, abstractmethod

from src.domain.auditoria.entities import AuditoriaDecision


class AuditoriaDecisionRepository(ABC):
    @abstractmethod
    async def guardar(self, auditoria: AuditoriaDecision) -> AuditoriaDecision:
        raise NotImplementedError

    @abstractmethod
    async def listar_por_cotizacion(
        self, cotizacion_id: uuid.UUID
    ) -> list[AuditoriaDecision]:
        raise NotImplementedError
