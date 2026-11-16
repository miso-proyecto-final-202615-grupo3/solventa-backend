from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.socios.entities import EventoSocio, Socio
from src.domain.socios.repositories import SocioRepository
from src.infrastructure.persistence.models import EventoSocioModel, SocioModel


class SqlAlchemySocioRepository(SocioRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def registrar(self, socio: Socio, evento: EventoSocio) -> None:
        self.session.add(
            SocioModel(
                id=socio.id,
                nombre=socio.nombre,
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
