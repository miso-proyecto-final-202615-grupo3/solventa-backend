import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.condiciones.condiciones_cotizacion_repository import CondicionesCotizacionRepository
from src.domain.condiciones.entities import CondicionesCotizacion
from src.infrastructure.persistence.models import CondicionesCotizacionModel


class SqlAlchemyCondicionesCotizacionRepository(CondicionesCotizacionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def guardar(self, condiciones: CondicionesCotizacion) -> None:
        self.session.add(CondicionesCotizacionModel(
            condiciones_cotizacion_id=condiciones.condiciones_cotizacion_id,
            cotizacion_id=condiciones.cotizacion_id,
            version_condiciones_generales=condiciones.version_condiciones_generales,
            condiciones_generales=condiciones.condiciones_generales,
            condiciones_particulares=condiciones.condiciones_particulares,
            creada_en=condiciones.creada_en,
        ))
        await self.session.flush()

    async def obtener_por_cotizacion(self, cotizacion_id: uuid.UUID) -> CondicionesCotizacion | None:
        result = await self.session.execute(
            select(CondicionesCotizacionModel)
            .where(CondicionesCotizacionModel.cotizacion_id == cotizacion_id)
            .order_by(CondicionesCotizacionModel.creada_en.desc(), CondicionesCotizacionModel.condiciones_cotizacion_id.desc())
            .limit(1)
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return CondicionesCotizacion(
            condiciones_cotizacion_id=model.condiciones_cotizacion_id,
            cotizacion_id=model.cotizacion_id,
            version_condiciones_generales=model.version_condiciones_generales,
            condiciones_generales=model.condiciones_generales,
            condiciones_particulares=model.condiciones_particulares,
            creada_en=model.creada_en,
        )
