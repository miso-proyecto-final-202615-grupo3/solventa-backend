import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.productos.entities import Cobertura, EstadoCobertura
from src.domain.productos.repositories import CoberturaRepository
from src.infrastructure.persistence.models import CoberturaModel


def _a_entidad(model: CoberturaModel) -> Cobertura:
    return Cobertura(
        cobertura_id=model.cobertura_id,
        producto_id=model.producto_id,
        codigo=model.codigo,
        nombre=model.nombre,
        limite_asegurado=model.limite_asegurado,
        deducible=model.deducible,
        estado=EstadoCobertura(model.estado),
    )


class SqlAlchemyCoberturaRepository(CoberturaRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def guardar(self, cobertura: Cobertura) -> Cobertura:
        self.session.add(
            CoberturaModel(
                cobertura_id=cobertura.cobertura_id,
                producto_id=cobertura.producto_id,
                codigo=cobertura.codigo,
                nombre=cobertura.nombre,
                limite_asegurado=cobertura.limite_asegurado,
                deducible=cobertura.deducible,
                estado=cobertura.estado.value,
            )
        )
        await self.session.flush()
        return cobertura

    async def listar_activas_por_producto(
        self, producto_id: uuid.UUID
    ) -> list[Cobertura]:
        return (await self.listar_activas_por_productos([producto_id])).get(
            producto_id, []
        )

    async def listar_activas_por_productos(
        self, producto_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[Cobertura]]:
        if not producto_ids:
            return {}
        result = await self.session.execute(
            select(CoberturaModel)
            .where(
                CoberturaModel.producto_id.in_(producto_ids),
                CoberturaModel.estado == EstadoCobertura.ACTIVA.value,
            )
            .order_by(CoberturaModel.codigo)
        )
        agrupadas: dict[uuid.UUID, list[Cobertura]] = defaultdict(list)
        for model in result.scalars().all():
            agrupadas[model.producto_id].append(_a_entidad(model))
        return dict(agrupadas)
