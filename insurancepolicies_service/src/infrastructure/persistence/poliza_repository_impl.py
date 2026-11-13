import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domain.polizas.entities import (
    ContratoPoliza,
    EstadoCertificado,
    Poliza,
    PolizaCobertura,
)
from src.domain.polizas.repositories import PolizaDuplicadaError, PolizaRepository
from src.infrastructure.persistence.models import (
    PolizaContratoModel,
    PolizaCoberturaModel,
    PolizaModel,
)


def _con_zona(valor: datetime | None) -> datetime | None:
    # SQLite devuelve fechas sin zona horaria; PostgreSQL las devuelve con ella.
    if valor is not None and valor.tzinfo is None:
        return valor.replace(tzinfo=UTC)
    return valor


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
        vigencia_desde=_con_zona(model.vigencia_desde),
        vigencia_hasta=_con_zona(model.vigencia_hasta),
        emitida_en=_con_zona(model.emitida_en),
        ramo=model.ramo,
        titular_nombre=model.titular_nombre,
        estado_certificado=EstadoCertificado(model.estado_certificado),
        ruta_certificado=model.ruta_certificado,
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
                titular_nombre=poliza.titular_nombre,
                estado_certificado=poliza.estado_certificado.value,
                ruta_certificado=poliza.ruta_certificado,
            )
        )
        try:
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
        except IntegrityError as exc:
            raise PolizaDuplicadaError() from exc
        return poliza

    async def obtener_por_id(self, poliza_id: uuid.UUID) -> Poliza | None:
        return await self._obtener(PolizaModel.poliza_id == poliza_id)

    async def obtener_por_numero(self, numero: str) -> Poliza | None:
        return await self._obtener(PolizaModel.numero == numero)

    async def obtener_por_cotizacion(self, cotizacion_id: uuid.UUID) -> Poliza | None:
        return await self._obtener(PolizaModel.cotizacion_id == cotizacion_id)

    async def listar_por_cliente(self, cliente_id: uuid.UUID) -> list[Poliza]:
        result = await self.session.execute(
            select(PolizaModel)
            .options(selectinload(PolizaModel.coberturas))
            .where(PolizaModel.cliente_id == cliente_id)
            .order_by(PolizaModel.vigencia_desde.desc())
        )
        return [_a_entidad(model) for model in result.scalars().all()]

    async def guardar_contrato(self, contrato: ContratoPoliza) -> None:
        self.session.add(PolizaContratoModel(poliza_id=contrato.poliza_id, datos=contrato.datos))
        await self.session.flush()

    async def obtener_contrato(self, poliza_id: uuid.UUID) -> ContratoPoliza | None:
        result = await self.session.execute(
            select(PolizaContratoModel)
            .where(PolizaContratoModel.poliza_id == poliza_id)
            .execution_options(populate_existing=True)
        )
        model = result.scalar_one_or_none()
        return ContratoPoliza(poliza_id=model.poliza_id, datos=model.datos) if model else None

    async def actualizar_certificado(
        self, poliza_id: uuid.UUID, estado: EstadoCertificado, ruta: str | None
    ) -> None:
        await self.session.execute(
            update(PolizaModel)
            .where(PolizaModel.poliza_id == poliza_id)
            .values(estado_certificado=estado.value, ruta_certificado=ruta)
            .execution_options(synchronize_session=False)
        )

    async def _obtener(self, condicion) -> Poliza | None:
        result = await self.session.execute(
            select(PolizaModel)
            .options(selectinload(PolizaModel.coberturas))
            .where(condicion)
            .execution_options(populate_existing=True)
        )
        model = result.scalar_one_or_none()
        return _a_entidad(model) if model else None
