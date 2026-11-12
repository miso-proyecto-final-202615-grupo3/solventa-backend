import uuid

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.verificaciones_kyc_aml.entities import (
    EstadoVerificacion,
    ResultadoChequeo,
    VerificacionKycAml,
)
from src.domain.verificaciones_kyc_aml.repositories import (
    VerificacionDuplicadaError,
    VerificacionKycAmlRepository,
)
from src.infrastructure.persistence.models import VerificacionKycAmlModel


class SqlAlchemyVerificacionKycAmlRepository(VerificacionKycAmlRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def crear(self, verificacion: VerificacionKycAml) -> None:
        self.session.add(
            VerificacionKycAmlModel(**self._a_valores(verificacion), id=verificacion.id,
                                    cliente_id=verificacion.cliente_id)
        )
        try:
            await self.session.flush()
        except IntegrityError as exc:
            raise VerificacionDuplicadaError() from exc

    async def obtener(
        self, cliente_id: uuid.UUID, verificacion_id: uuid.UUID
    ) -> VerificacionKycAml | None:
        result = await self.session.execute(
            select(VerificacionKycAmlModel).where(
                VerificacionKycAmlModel.id == verificacion_id,
                VerificacionKycAmlModel.cliente_id == cliente_id,
            ).execution_options(populate_existing=True)
        )
        return self._a_entidad(result.scalar_one_or_none())

    async def obtener_por_idempotency_key(
        self, cliente_id: uuid.UUID, idempotency_key: str
    ) -> VerificacionKycAml | None:
        result = await self.session.execute(
            select(VerificacionKycAmlModel).where(
                VerificacionKycAmlModel.cliente_id == cliente_id,
                VerificacionKycAmlModel.idempotency_key == idempotency_key,
            ).execution_options(populate_existing=True)
        )
        return self._a_entidad(result.scalar_one_or_none())

    async def obtener_ultima_id(self, cliente_id: uuid.UUID) -> uuid.UUID | None:
        result = await self.session.execute(
            select(VerificacionKycAmlModel.id)
            .where(VerificacionKycAmlModel.cliente_id == cliente_id)
            .order_by(
                VerificacionKycAmlModel.iniciada_en.desc(),
                VerificacionKycAmlModel.id.desc(),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def actualizar(self, verificacion: VerificacionKycAml) -> bool:
        result = await self.session.execute(
            update(VerificacionKycAmlModel)
            .where(
                VerificacionKycAmlModel.id == verificacion.id,
                VerificacionKycAmlModel.version == verificacion.version,
            )
            .values(**self._a_valores(verificacion), version=verificacion.version + 1)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            return False
        verificacion.version += 1
        return True

    @staticmethod
    def _a_valores(v: VerificacionKycAml) -> dict:
        return {
            "proveedor": v.proveedor,
            "proveedor_verificacion_id": v.proveedor_verificacion_id,
            "idempotency_key": v.idempotency_key,
            "huella_documentos": v.huella_documentos,
            "estado": v.estado.value,
            "resultado_kyc": v.resultado_kyc.value if v.resultado_kyc else None,
            "resultado_aml": v.resultado_aml.value if v.resultado_aml else None,
            "ruta_documento_frontal": v.ruta_documento_frontal,
            "ruta_documento_reverso": v.ruta_documento_reverso,
            "respuesta_inicio": v.respuesta_inicio,
            "respuesta_resultado": v.respuesta_resultado,
            "error_codigo": v.error_codigo,
            "error_detalle": v.error_detalle,
            "correlation_id": v.correlation_id,
            "iniciada_en": v.iniciada_en,
            "resultado_en": v.resultado_en,
        }

    @staticmethod
    def _a_entidad(m: VerificacionKycAmlModel | None) -> VerificacionKycAml | None:
        if m is None:
            return None
        return VerificacionKycAml(
            id=m.id,
            cliente_id=m.cliente_id,
            proveedor=m.proveedor,
            huella_documentos=m.huella_documentos,
            ruta_documento_frontal=m.ruta_documento_frontal,
            ruta_documento_reverso=m.ruta_documento_reverso,
            iniciada_en=m.iniciada_en,
            correlation_id=m.correlation_id,
            estado=EstadoVerificacion(m.estado),
            idempotency_key=m.idempotency_key,
            proveedor_verificacion_id=m.proveedor_verificacion_id,
            resultado_kyc=ResultadoChequeo(m.resultado_kyc) if m.resultado_kyc else None,
            resultado_aml=ResultadoChequeo(m.resultado_aml) if m.resultado_aml else None,
            respuesta_inicio=m.respuesta_inicio,
            respuesta_resultado=m.respuesta_resultado,
            error_codigo=m.error_codigo,
            error_detalle=m.error_detalle,
            resultado_en=m.resultado_en,
            version=m.version,
        )
