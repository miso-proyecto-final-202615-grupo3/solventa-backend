from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from src.domain.consentimiento.auditoria import (
    AuditoriaConsentimiento,
    AuditoriaConsentimientoRepository,
    ClienteAuditado,
    EventoAuditoriaConsentimiento,
)
from src.domain.consentimiento.entities import EstadoConsentimiento
from src.infrastructure.persistence.consentimiento_repository_impl import (
    SqlAlchemyConsentimientoRepository,
)
from src.infrastructure.persistence.models import (
    AuditoriaConsentimientoModel,
    ClienteModel,
    ConsentimientoModel,
)


class SqlAlchemyAuditoriaConsentimientoRepository(
    AuditoriaConsentimientoRepository
):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def buscar_por_correo(
        self, correo: str
    ) -> AuditoriaConsentimiento | None:
        return await self._buscar(
            func.lower(ClienteModel.correo) == correo.lower()
        )

    async def buscar_por_identificacion(
        self, numero_identificacion: str
    ) -> AuditoriaConsentimiento | None:
        return await self._buscar(
            ClienteModel.numero_identificacion == numero_identificacion
        )

    async def _buscar(
        self, criterio: ColumnElement[bool]
    ) -> AuditoriaConsentimiento | None:
        cliente = (
            await self.session.execute(select(ClienteModel).where(criterio))
        ).scalars().first()
        if cliente is None:
            return None

        estado = await self.session.scalar(
            select(ConsentimientoModel.estado).where(
                ConsentimientoModel.cliente_id == cliente.id,
                ConsentimientoModel.fuente_datos
                == SqlAlchemyConsentimientoRepository.FUENTE_DATOS,
                ConsentimientoModel.proposito
                == SqlAlchemyConsentimientoRepository.PROPOSITO,
            )
        )
        eventos = (
            await self.session.execute(
                select(AuditoriaConsentimientoModel)
                .where(AuditoriaConsentimientoModel.cliente_id == cliente.id)
                .order_by(AuditoriaConsentimientoModel.fecha.desc())
            )
        ).scalars()

        return AuditoriaConsentimiento(
            cliente=ClienteAuditado(
                id=cliente.id,
                nombres=cliente.nombres,
                apellidos=cliente.apellidos,
                tipo_documento=cliente.tipo_documento,
                numero_identificacion=cliente.numero_identificacion,
                correo=cliente.correo,
                estado_consentimiento=(
                    EstadoConsentimiento(estado) if estado else None
                ),
            ),
            eventos=[
                EventoAuditoriaConsentimiento(
                    id=evento.id,
                    tipo_accion=evento.tipo_accion,
                    fecha=evento.fecha,
                    version_terminos=evento.version_terminos,
                    canal=evento.canal,
                )
                for evento in eventos
            ],
        )
