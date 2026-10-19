import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.consentimiento.entities import (
    ConsentimientoActual,
    EstadoConsentimiento,
    TipoAccionConsentimiento,
)
from src.domain.consentimiento.repositories import ConsentimientoRepository
from src.infrastructure.persistence.models import (
    AuditoriaConsentimientoModel,
    ConsentimientoModel,
)


class SqlAlchemyConsentimientoRepository(ConsentimientoRepository):
    FUENTE_DATOS = "OPEN_FINANCE"
    PROPOSITO = "TRATAMIENTO_DATOS_PERSONALES_Y_FINANCIEROS"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def obtener_actual(
        self, cliente_id: uuid.UUID
    ) -> ConsentimientoActual | None:
        result = await self.session.execute(
            select(ConsentimientoModel).where(
                ConsentimientoModel.cliente_id == cliente_id,
                ConsentimientoModel.fuente_datos == self.FUENTE_DATOS,
                ConsentimientoModel.proposito == self.PROPOSITO,
            )
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return ConsentimientoActual(
            cliente_id=model.cliente_id,
            estado=EstadoConsentimiento(model.estado),
            otorgado_en=model.otorgado_en,
            revocado_en=model.revocado_en,
        )

    async def actualizar_estado(
        self,
        cliente_id: uuid.UUID,
        estado: EstadoConsentimiento,
        version_terminos: str,
        canal: str,
    ) -> ConsentimientoActual | None:
        result = await self.session.execute(
            select(ConsentimientoModel)
            .where(
                ConsentimientoModel.cliente_id == cliente_id,
                ConsentimientoModel.fuente_datos == self.FUENTE_DATOS,
                ConsentimientoModel.proposito == self.PROPOSITO,
            )
            .with_for_update()
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        ahora = datetime.now(UTC)
        model.estado = estado.value
        if estado == EstadoConsentimiento.ACEPTADO:
            model.otorgado_en = ahora
            model.revocado_en = None
            tipo_accion = TipoAccionConsentimiento.ACEPTACION
        else:
            model.revocado_en = ahora
            tipo_accion = TipoAccionConsentimiento.REVOCACION
        self.session.add(
            AuditoriaConsentimientoModel(
                cliente_id=cliente_id,
                tipo_accion=tipo_accion.value,
                fecha=ahora,
                version_terminos=version_terminos,
                canal=canal,
            )
        )
        await self.session.commit()
        return ConsentimientoActual(
            cliente_id=cliente_id,
            estado=estado,
            otorgado_en=model.otorgado_en,
            revocado_en=model.revocado_en,
        )