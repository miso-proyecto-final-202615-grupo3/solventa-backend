import uuid
from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from src.domain.siniestros.entities import (
    ActivacionParametrica,
    ActivacionPoliza,
    EventoExterno,
    Indemnizacion,
    Siniestro,
)

Entity = TypeVar("Entity")


class Repository(ABC, Generic[Entity]):
    @abstractmethod
    async def guardar(self, entity: Entity) -> Entity:
        raise NotImplementedError

    @abstractmethod
    async def obtener_por_id(self, entity_id: uuid.UUID) -> Entity | None:
        raise NotImplementedError


class EventoExternoRepository(Repository[EventoExterno]):
    pass


class ActivacionParametricaRepository(Repository[ActivacionParametrica]):
    pass


class ActivacionPolizaRepository(Repository[ActivacionPoliza]):
    pass


class SiniestroRepository(Repository[Siniestro]):
    pass


class IndemnizacionRepository(Repository[Indemnizacion]):
    pass
