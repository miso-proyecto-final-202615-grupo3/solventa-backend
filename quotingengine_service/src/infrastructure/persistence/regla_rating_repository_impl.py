import uuid
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.reglas_rating.entities import EstadoReglaRating, ReglaRating
from src.domain.reglas_rating.repositories import ReglaRatingRepository
from src.infrastructure.persistence.models import ReglaRatingModel


def _a_entidad(model: ReglaRatingModel) -> ReglaRating:
    return ReglaRating(
        regla_rating_id=model.regla_rating_id,
        producto_id=model.producto_id,
        version=model.version,
        estado=EstadoReglaRating(model.estado),
        definicion=model.definicion,
        vigente_desde=model.vigente_desde,
        vigente_hasta=model.vigente_hasta,
    )


class SqlAlchemyReglaRatingRepository(ReglaRatingRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def guardar(self, regla: ReglaRating) -> ReglaRating:
        self.session.add(
            ReglaRatingModel(
                regla_rating_id=regla.regla_rating_id,
                producto_id=regla.producto_id,
                version=regla.version,
                estado=regla.estado.value,
                definicion=regla.definicion,
                vigente_desde=regla.vigente_desde,
                vigente_hasta=regla.vigente_hasta,
            )
        )
        await self.session.flush()
        return regla

    async def obtener_vigente_por_producto(
        self, producto_id: uuid.UUID
    ) -> ReglaRating | None:
        return (await self.obtener_vigentes_por_productos([producto_id])).get(
            producto_id
        )

    async def obtener_vigentes_por_productos(
        self, producto_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, ReglaRating]:
        if not producto_ids:
            return {}
        ahora = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(ReglaRatingModel)
            .where(
                ReglaRatingModel.producto_id.in_(producto_ids),
                ReglaRatingModel.estado == EstadoReglaRating.VIGENTE.value,
                or_(
                    ReglaRatingModel.vigente_hasta.is_(None),
                    ReglaRatingModel.vigente_hasta > ahora,
                ),
            )
            .order_by(ReglaRatingModel.vigente_desde.asc())
        )
        # la última regla vigente por producto prevalece
        return {m.producto_id: _a_entidad(m) for m in result.scalars().all()}

    async def existe_por_producto(self, producto_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            select(func.count())
            .select_from(ReglaRatingModel)
            .where(ReglaRatingModel.producto_id == producto_id)
        )
        return result.scalar_one() > 0
