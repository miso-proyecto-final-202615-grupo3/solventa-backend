from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.socios.entities import EstadoSocio, EventoSocio, Socio
from src.domain.socios.repositories import SocioRepository
from src.infrastructure.persistence.models import EventoSocioModel, SocioModel


class SqlAlchemySocioRepository(SocioRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def existe_por_correo(self, correo: str) -> bool:
        return (
            await self.session.scalar(
                select(SocioModel.id).where(SocioModel.correo == correo.strip().lower())
            )
            is not None
        )

    async def registrar(self, socio: Socio, evento: EventoSocio) -> None:
        self.session.add(
            SocioModel(
                id=socio.id,
                nombre=socio.nombre,
                correo=socio.correo,
                tipo_socio=socio.tipo_socio,
                canal_integracion=socio.canal_integracion,
                estado=socio.estado.value,
                creado_en=socio.creado_en,
                registrado_por=socio.registrado_por,
            )
        )
        await self.session.flush()
        self.session.add(
            EventoSocioModel(
                id=evento.id,
                socio_id=evento.socio_id,
                accion=evento.accion,
                actor_id=evento.actor_id,
                ocurrido_en=evento.ocurrido_en,
            )
        )
        await self.session.commit()

    async def listar(self) -> list[Socio]:
        result = await self.session.scalars(select(SocioModel).order_by(SocioModel.creado_en.desc()))
        return [
            Socio(
                id=row.id,
                nombre=row.nombre,
                correo=row.correo,
                tipo_socio=row.tipo_socio,
                canal_integracion=row.canal_integracion,
                estado=EstadoSocio(row.estado),
                creado_en=row.creado_en,
                registrado_por=row.registrado_por,
            )
            for row in result
        ]
