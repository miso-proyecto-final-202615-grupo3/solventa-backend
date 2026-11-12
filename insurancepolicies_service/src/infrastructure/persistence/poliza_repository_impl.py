import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domain.polizas.entities import Poliza, PolizaCobertura
from src.domain.polizas.repositories import PolizaRepository
from src.infrastructure.persistence.models import PolizaCoberturaModel, PolizaModel


def _cobertura_a_entidad(model: PolizaCoberturaModel) -> PolizaCobertura:
    return PolizaCobertura(
        poliza_cobertura_id=model.poliza_cobertura_id,
        poliza_id=model.poliza_id,
        cobertura_id=model.cobertura_id,
        limite_asegurado=model.limite_asegurado,
        deducible=model.deducible,
        prima=model.prima,
    )


def _a_entidad(model: PolizaModel) -> Poliza:
    return Poliza(
        poliza_id=model.poliza_id,
        cliente_id=model.cliente_id,
        cotizacion_id=model.cotizacion_id,
        producto_id=model.producto_id,
        numero=model.numero,
        estado=model.estado,
        vigencia_desde=model.vigencia_desde,
        vigencia_hasta=model.vigencia_hasta,
        emitida_en=model.emitida_en,
        ramo=model.ramo,
        coberturas=[_cobertura_a_entidad(c) for c in model.coberturas],
    )


class SqlAlchemyPolizaRepository(PolizaRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def guardar(self, poliza: Poliza) -> Poliza:
        self.session.add(
            PolizaModel(
                poliza_id=poliza.poliza_id,
                cliente_id=poliza.cliente_id,
                cotizacion_id=poliza.cotizacion_id,
                producto_id=poliza.producto_id,
                numero=poliza.numero,
                estado=poliza.estado,
                vigencia_desde=poliza.vigencia_desde,
                vigencia_hasta=poliza.vigencia_hasta,
                emitida_en=poliza.emitida_en,
                ramo=poliza.ramo,
            )
        )
        await self.session.flush()
        self.session.add_all(
            PolizaCoberturaModel(
                poliza_cobertura_id=cobertura.poliza_cobertura_id,
                poliza_id=poliza.poliza_id,
                cobertura_id=cobertura.cobertura_id,
                limite_asegurado=cobertura.limite_asegurado,
                deducible=cobertura.deducible,
                prima=cobertura.prima,
            )
            for cobertura in poliza.coberturas
        )
        await self.session.flush()
        return poliza

    async def obtener_por_id(self, poliza_id: uuid.UUID) -> Poliza | None:
        result = await self.session.execute(
            select(PolizaModel)
            .options(selectinload(PolizaModel.coberturas))
            .where(PolizaModel.poliza_id == poliza_id)
        )
        model = result.scalar_one_or_none()
        return _a_entidad(model) if model else None

    async def obtener_por_numero(self, numero: str) -> Poliza | None:
        result = await self.session.execute(
            select(PolizaModel)
            .options(selectinload(PolizaModel.coberturas))
            .where(PolizaModel.numero == numero)
        )
        model = result.scalar_one_or_none()
        return _a_entidad(model) if model else None

    async def listar_por_cliente(self, cliente_id: uuid.UUID) -> list[Poliza]:
        result = await self.session.execute(
            select(PolizaModel)
            .options(selectinload(PolizaModel.coberturas))
            .where(PolizaModel.cliente_id == cliente_id)
            .order_by(PolizaModel.vigencia_desde.desc())
        )
        return [_a_entidad(model) for model in result.scalars().all()]
