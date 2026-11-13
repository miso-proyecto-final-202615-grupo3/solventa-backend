import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.certificados.entities import EstadoGeneracion, GeneracionCertificado
from src.domain.certificados.repositories import (
    GeneracionCertificadoRepository,
    GeneracionEnCursoDuplicadaError,
)
from src.infrastructure.persistence.models import GeneracionCertificadoModel


def _con_zona(valor: datetime | None) -> datetime | None:
    # SQLite devuelve fechas sin zona horaria; PostgreSQL las devuelve con ella.
    if valor is not None and valor.tzinfo is None:
        return valor.replace(tzinfo=UTC)
    return valor


def _a_entidad(model: GeneracionCertificadoModel | None) -> GeneracionCertificado | None:
    if model is None:
        return None
    return GeneracionCertificado(
        generacion_id=model.generacion_id,
        poliza_id=model.poliza_id,
        cliente_id=model.cliente_id,
        estado=EstadoGeneracion(model.estado),
        plantilla=model.plantilla,
        datos_plantilla=model.datos_plantilla,
        ruta_certificado=model.ruta_certificado,
        error_codigo=model.error_codigo,
        error_detalle=model.error_detalle,
        correlation_id=model.correlation_id,
        iniciada_en=_con_zona(model.iniciada_en),
        finalizada_en=_con_zona(model.finalizada_en),
    )


class SqlAlchemyGeneracionCertificadoRepository(GeneracionCertificadoRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def crear(self, generacion: GeneracionCertificado) -> None:
        self.session.add(
            GeneracionCertificadoModel(
                generacion_id=generacion.generacion_id,
                poliza_id=generacion.poliza_id,
                cliente_id=generacion.cliente_id,
                estado=generacion.estado.value,
                plantilla=generacion.plantilla,
                datos_plantilla=generacion.datos_plantilla,
                ruta_certificado=generacion.ruta_certificado,
                error_codigo=generacion.error_codigo,
                error_detalle=generacion.error_detalle,
                correlation_id=generacion.correlation_id,
                iniciada_en=generacion.iniciada_en,
                finalizada_en=generacion.finalizada_en,
            )
        )
        try:
            await self.session.flush()
        except IntegrityError as exc:
            raise GeneracionEnCursoDuplicadaError() from exc

    async def actualizar(self, generacion: GeneracionCertificado) -> bool:
        result = await self.session.execute(
            update(GeneracionCertificadoModel)
            .where(
                GeneracionCertificadoModel.generacion_id == generacion.generacion_id,
                GeneracionCertificadoModel.estado == EstadoGeneracion.EN_PROCESO.value,
            )
            .values(
                estado=generacion.estado.value,
                finalizada_en=generacion.finalizada_en,
                ruta_certificado=generacion.ruta_certificado,
                error_codigo=generacion.error_codigo,
                error_detalle=generacion.error_detalle,
            )
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1

    async def obtener_en_proceso(self, poliza_id: uuid.UUID) -> GeneracionCertificado | None:
        result = await self.session.execute(
            select(GeneracionCertificadoModel)
            .where(
                GeneracionCertificadoModel.poliza_id == poliza_id,
                GeneracionCertificadoModel.estado == EstadoGeneracion.EN_PROCESO.value,
            )
            .execution_options(populate_existing=True)
        )
        return _a_entidad(result.scalar_one_or_none())

    async def obtener_ultima(self, poliza_id: uuid.UUID) -> GeneracionCertificado | None:
        result = await self.session.execute(
            select(GeneracionCertificadoModel)
            .where(GeneracionCertificadoModel.poliza_id == poliza_id)
            .order_by(
                GeneracionCertificadoModel.iniciada_en.desc(),
                GeneracionCertificadoModel.generacion_id.desc(),
            )
            .limit(1)
            .execution_options(populate_existing=True)
        )
        return _a_entidad(result.scalar_one_or_none())
