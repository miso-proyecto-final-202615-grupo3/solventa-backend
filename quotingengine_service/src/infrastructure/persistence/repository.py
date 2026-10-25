import uuid
from collections.abc import Sequence
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import Base
from src.infrastructure.persistence.models import (
    AuditoriaDecisionModel,
    CoberturaModel,
    CotizacionCoberturaModel,
    CotizacionModel,
    ProductoSeguroModel,
    ReglaRatingModel,
)

ModelT = TypeVar("ModelT", bound=Base)


class SQLAlchemyRepository(Generic[ModelT]):
    """Repositorio CRUD básico sobre un modelo del motor de cotización."""

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entity: ModelT) -> ModelT:
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def get(self, entity_id: uuid.UUID) -> ModelT | None:
        return await self._session.get(self.model, entity_id)

    async def list(self, limit: int = 100, offset: int = 0) -> Sequence[ModelT]:
        result = await self._session.execute(
            select(self.model).limit(limit).offset(offset)
        )
        return result.scalars().all()

    async def delete(self, entity: ModelT) -> None:
        await self._session.delete(entity)
        await self._session.flush()


class ProductoSeguroRepository(SQLAlchemyRepository[ProductoSeguroModel]):
    model = ProductoSeguroModel

    async def get_by_codigo(self, codigo: str) -> ProductoSeguroModel | None:
        result = await self._session.execute(
            select(ProductoSeguroModel).where(ProductoSeguroModel.codigo == codigo)
        )
        return result.scalar_one_or_none()


class CoberturaRepository(SQLAlchemyRepository[CoberturaModel]):
    model = CoberturaModel

    async def list_by_producto(self, producto_id: uuid.UUID) -> Sequence[CoberturaModel]:
        result = await self._session.execute(
            select(CoberturaModel).where(CoberturaModel.producto_id == producto_id)
        )
        return result.scalars().all()


class ReglaRatingRepository(SQLAlchemyRepository[ReglaRatingModel]):
    model = ReglaRatingModel

    async def list_by_producto(
        self, producto_id: uuid.UUID
    ) -> Sequence[ReglaRatingModel]:
        result = await self._session.execute(
            select(ReglaRatingModel).where(ReglaRatingModel.producto_id == producto_id)
        )
        return result.scalars().all()


class CotizacionRepository(SQLAlchemyRepository[CotizacionModel]):
    model = CotizacionModel

    async def list_by_cliente(self, cliente_id: uuid.UUID) -> Sequence[CotizacionModel]:
        result = await self._session.execute(
            select(CotizacionModel).where(CotizacionModel.cliente_id == cliente_id)
        )
        return result.scalars().all()


class CotizacionCoberturaRepository(SQLAlchemyRepository[CotizacionCoberturaModel]):
    model = CotizacionCoberturaModel

    async def list_by_cotizacion(
        self, cotizacion_id: uuid.UUID
    ) -> Sequence[CotizacionCoberturaModel]:
        result = await self._session.execute(
            select(CotizacionCoberturaModel).where(
                CotizacionCoberturaModel.cotizacion_id == cotizacion_id
            )
        )
        return result.scalars().all()


class AuditoriaDecisionRepository(SQLAlchemyRepository[AuditoriaDecisionModel]):
    model = AuditoriaDecisionModel

    async def list_by_cotizacion(
        self, cotizacion_id: uuid.UUID
    ) -> Sequence[AuditoriaDecisionModel]:
        result = await self._session.execute(
            select(AuditoriaDecisionModel).where(
                AuditoriaDecisionModel.cotizacion_id == cotizacion_id
            )
        )
        return result.scalars().all()
