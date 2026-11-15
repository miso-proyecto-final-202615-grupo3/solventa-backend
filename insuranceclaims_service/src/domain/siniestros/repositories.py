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
from src.domain.siniestros.evidencias import EvidenciaSiniestro

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
    @abstractmethod
    async def obtener_por_clave_idempotencia(self, clave: str) -> Siniestro | None:
        raise NotImplementedError

    @abstractmethod
    async def obtener_de_cliente(self, siniestro_id: uuid.UUID, cliente_id: uuid.UUID) -> Siniestro | None:
        raise NotImplementedError

    @abstractmethod
    async def obtener_de_cliente_para_actualizar(
        self, siniestro_id: uuid.UUID, cliente_id: uuid.UUID
    ) -> Siniestro | None:
        """Igual que `obtener_de_cliente`, pero bloquea la fila (`FOR UPDATE`) hasta el commit."""
        raise NotImplementedError

    @abstractmethod
    async def actualizar(self, siniestro: Siniestro) -> Siniestro:
        raise NotImplementedError


class EvidenciaRepository(Repository[EvidenciaSiniestro]):
    @abstractmethod
    async def actualizar(self, evidencia: EvidenciaSiniestro) -> EvidenciaSiniestro:
        raise NotImplementedError

    @abstractmethod
    async def obtener_de_siniestro(self, evidencia_id: uuid.UUID, siniestro_id: uuid.UUID) -> EvidenciaSiniestro | None:
        raise NotImplementedError

    @abstractmethod
    async def listar_de_siniestro(self, siniestro_id: uuid.UUID) -> list[EvidenciaSiniestro]:
        raise NotImplementedError

    @abstractmethod
    async def obtener_por_clave(self, siniestro_id: uuid.UUID, clave: str) -> EvidenciaSiniestro | None:
        raise NotImplementedError


class IndemnizacionRepository(Repository[Indemnizacion]):
    pass
