import uuid
from dataclasses import asdict, fields
from typing import Generic, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import Base
from src.domain.siniestros.entities import (
    ActivacionParametrica,
    ActivacionPoliza,
    EventoExterno,
    Indemnizacion,
    Siniestro,
)
from src.domain.siniestros.repositories import (
    ActivacionParametricaRepository,
    ActivacionPolizaRepository,
    EventoExternoRepository,
    IndemnizacionRepository,
    SiniestroRepository,
)
from src.infrastructure.persistence.models import (
    ActivacionParametricaModel,
    ActivacionPolizaModel,
    EventoExternoModel,
    IndemnizacionModel,
    SiniestroModel,
)

Entity = TypeVar(
    "Entity", EventoExterno, ActivacionParametrica, ActivacionPoliza, Siniestro, Indemnizacion
)
Model = TypeVar("Model", bound=Base)


class _SqlAlchemyEntityRepository(Generic[Entity, Model]):
    entity_type: type[Entity]
    model_type: type[Model]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def guardar(self, entity: Entity) -> Entity:
        self.session.add(self.model_type(**asdict(entity)))
        await self.session.flush()
        return entity

    async def obtener_por_id(self, entity_id: uuid.UUID) -> Entity | None:
        model = await self.session.get(self.model_type, entity_id)
        if model is None:
            return None
        return self.entity_type(**{
            field.name: getattr(model, field.name) for field in fields(self.entity_type)
        })


class SqlAlchemyEventoExternoRepository(
    _SqlAlchemyEntityRepository[EventoExterno, EventoExternoModel], EventoExternoRepository
):
    entity_type = EventoExterno
    model_type = EventoExternoModel


class SqlAlchemyActivacionParametricaRepository(
    _SqlAlchemyEntityRepository[ActivacionParametrica, ActivacionParametricaModel],
    ActivacionParametricaRepository,
):
    entity_type = ActivacionParametrica
    model_type = ActivacionParametricaModel


class SqlAlchemyActivacionPolizaRepository(
    _SqlAlchemyEntityRepository[ActivacionPoliza, ActivacionPolizaModel], ActivacionPolizaRepository
):
    entity_type = ActivacionPoliza
    model_type = ActivacionPolizaModel


class SqlAlchemySiniestroRepository(
    _SqlAlchemyEntityRepository[Siniestro, SiniestroModel], SiniestroRepository
):
    entity_type = Siniestro
    model_type = SiniestroModel


class SqlAlchemyIndemnizacionRepository(
    _SqlAlchemyEntityRepository[Indemnizacion, IndemnizacionModel], IndemnizacionRepository
):
    entity_type = Indemnizacion
    model_type = IndemnizacionModel
