import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.cotizaciones.entities import CotizacionCobertura
from src.domain.cotizaciones.repositories import CotizacionCoberturaRepository
from src.infrastructure.persistence.models import CotizacionCoberturaModel


def _a_entidad(model: CotizacionCoberturaModel) -> CotizacionCobertura:
    return CotizacionCobertura(
        cotizacion_cobertura_id=model.cotizacion_cobertura_id,
        cotizacion_id=model.cotizacion_id,
        cobertura_id=model.cobertura_id,
        prima=model.prima,
        limite_asegurado=model.limite_asegurado,
        deducible=model.deducible,
    )


class SqlAlchemyCotizacionCoberturaRepository(CotizacionCoberturaRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def guardar_todas(
        self, detalles: list[CotizacionCobertura]
    ) -> list[CotizacionCobertura]:
        self.session.add_all(
            CotizacionCoberturaModel(
                cotizacion_cobertura_id=d.cotizacion_cobertura_id,
                cotizacion_id=d.cotizacion_id,
                cobertura_id=d.cobertura_id,
                prima=d.prima,
                limite_asegurado=d.limite_asegurado,
                deducible=d.deducible,
            )
            for d in detalles
        )
        await self.session.flush()
        return detalles

    async def listar_por_cotizacion(
        self, cotizacion_id: uuid.UUID
    ) -> list[CotizacionCobertura]:
        result = await self.session.execute(
            select(CotizacionCoberturaModel).where(
                CotizacionCoberturaModel.cotizacion_id == cotizacion_id
            )
        )
        return [_a_entidad(m) for m in result.scalars().all()]
