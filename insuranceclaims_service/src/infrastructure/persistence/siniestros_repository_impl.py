import uuid
from dataclasses import asdict, fields
from typing import Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import Base
from src.domain.siniestros.entities import (
    ActivacionParametrica,
    ActivacionPoliza,
    EventoExterno,
    Indemnizacion,
    Siniestro,
)
from src.domain.siniestros.evidencias import EvidenciaSiniestro
from src.domain.siniestros.repositories import (
    ActivacionParametricaRepository,
    ActivacionPolizaRepository,
    EventoExternoRepository,
    EvidenciaRepository,
    IndemnizacionRepository,
    SiniestroRepository,
)
from src.infrastructure.persistence.models import (
    ActivacionParametricaModel,
    ActivacionPolizaModel,
    EventoExternoModel,
    EvidenciaSiniestroModel,
    IndemnizacionModel,
    SiniestroModel,
)

Entity = TypeVar(
    "Entity", EventoExterno, ActivacionParametrica, ActivacionPoliza, Siniestro, Indemnizacion, EvidenciaSiniestro
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
        return self._a_entidad(await self.session.get(self.model_type, entity_id))

    async def actualizar(self, entity: Entity) -> Entity:
        await self.session.merge(self.model_type(**asdict(entity)))
        await self.session.flush()
        return entity

    def _a_entidad(self, model: Model | None) -> Entity | None:
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

    async def obtener_por_clave_idempotencia(self, clave: str) -> Siniestro | None:
        model = await self.session.scalar(select(SiniestroModel).where(SiniestroModel.clave_idempotencia == clave))
        return self._a_entidad(model)

    async def obtener_de_cliente(self, siniestro_id: uuid.UUID, cliente_id: uuid.UUID) -> Siniestro | None:
        model = await self.session.scalar(
            select(SiniestroModel).where(
                SiniestroModel.siniestro_id == siniestro_id,
                SiniestroModel.cliente_id == cliente_id,
            )
        )
        return self._a_entidad(model)

    async def obtener_de_cliente_para_actualizar(
        self, siniestro_id: uuid.UUID, cliente_id: uuid.UUID
    ) -> Siniestro | None:
        # FOR UPDATE serializa las solicitudes concurrentes del mismo siniestro (en SQLite se ignora).
        model = await self.session.scalar(
            select(SiniestroModel)
            .where(SiniestroModel.siniestro_id == siniestro_id, SiniestroModel.cliente_id == cliente_id)
            .with_for_update()
        )
        return self._a_entidad(model)

    async def listar_de_cliente(
        self, cliente_id: uuid.UUID, poliza_id: uuid.UUID | None, limite: int, desplazamiento: int
    ) -> tuple[list[Siniestro], int]:
        filtro = [SiniestroModel.cliente_id == cliente_id]
        if poliza_id is not None:
            filtro.append(SiniestroModel.poliza_id == poliza_id)
        total = await self.session.scalar(select(func.count()).select_from(SiniestroModel).where(*filtro))
        modelos = await self.session.scalars(
            select(SiniestroModel)
            .where(*filtro)
            .order_by(SiniestroModel.reportado_en.desc(), SiniestroModel.siniestro_id)
            .limit(limite)
            .offset(desplazamiento)
        )
        return [self._a_entidad(m) for m in modelos.all()], int(total or 0)


class SqlAlchemyEvidenciaRepository(
    _SqlAlchemyEntityRepository[EvidenciaSiniestro, EvidenciaSiniestroModel], EvidenciaRepository
):
    entity_type = EvidenciaSiniestro
    model_type = EvidenciaSiniestroModel

    async def obtener_de_siniestro(self, evidencia_id: uuid.UUID, siniestro_id: uuid.UUID) -> EvidenciaSiniestro | None:
        model = await self.session.scalar(
            select(EvidenciaSiniestroModel).where(
                EvidenciaSiniestroModel.evidencia_id == evidencia_id,
                EvidenciaSiniestroModel.siniestro_id == siniestro_id,
            )
        )
        return self._a_entidad(model)

    async def obtener_por_clave(self, siniestro_id: uuid.UUID, clave: str) -> EvidenciaSiniestro | None:
        result = await self.session.execute(
            select(EvidenciaSiniestroModel).where(
                EvidenciaSiniestroModel.siniestro_id == siniestro_id,
                EvidenciaSiniestroModel.clave_idempotencia == clave,
            )
        )
        return self._a_entidad(result.scalar_one_or_none())

    async def listar_de_siniestro(self, siniestro_id: uuid.UUID) -> list[EvidenciaSiniestro]:
        modelos = await self.session.scalars(
            select(EvidenciaSiniestroModel)
            .where(EvidenciaSiniestroModel.siniestro_id == siniestro_id)
            .order_by(EvidenciaSiniestroModel.solicitada_en)
        )
        return [self._a_entidad(m) for m in modelos.all()]


class SqlAlchemyIndemnizacionRepository(
    _SqlAlchemyEntityRepository[Indemnizacion, IndemnizacionModel], IndemnizacionRepository
):
    entity_type = Indemnizacion
    model_type = IndemnizacionModel
