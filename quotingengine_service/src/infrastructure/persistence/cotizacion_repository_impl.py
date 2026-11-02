import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.cotizaciones.entities import Cotizacion, EstadoCotizacion
from src.domain.cotizaciones.repositories import CotizacionRepository
from src.infrastructure.persistence.models import CotizacionModel


def _a_entidad(model: CotizacionModel) -> Cotizacion:
    return Cotizacion(
        cotizacion_id=model.cotizacion_id,
        cliente_id=model.cliente_id,
        producto_id=model.producto_id,
        socio_id=model.socio_id,
        perfil_riesgo_id=model.perfil_riesgo_id,
        estado=EstadoCotizacion(model.estado),
        prima_total=model.prima_total,
        moneda=model.moneda,
        expira_en=model.expira_en,
        creada_en=model.creada_en,
    )


class SqlAlchemyCotizacionRepository(CotizacionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def guardar(self, cotizacion: Cotizacion) -> Cotizacion:
        model = CotizacionModel(
            cotizacion_id=cotizacion.cotizacion_id,
            cliente_id=cotizacion.cliente_id,
            producto_id=cotizacion.producto_id,
            socio_id=cotizacion.socio_id,
            perfil_riesgo_id=cotizacion.perfil_riesgo_id,
            estado=cotizacion.estado.value,
            prima_total=cotizacion.prima_total,
            moneda=cotizacion.moneda,
            expira_en=cotizacion.expira_en,
        )
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        cotizacion.creada_en = model.creada_en
        return cotizacion

    async def obtener_por_id(self, cotizacion_id: uuid.UUID) -> Cotizacion | None:
        model = await self.session.get(CotizacionModel, cotizacion_id)
        return _a_entidad(model) if model else None

    async def listar_por_cliente(self, cliente_id: uuid.UUID) -> list[Cotizacion]:
        result = await self.session.execute(
            select(CotizacionModel)
            .where(CotizacionModel.cliente_id == cliente_id)
            .order_by(CotizacionModel.creada_en.desc())
        )
        return [_a_entidad(m) for m in result.scalars().all()]
