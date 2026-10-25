from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.activacion_movil.entities import (
    DatosDispositivo,
    EstadoIntento,
    EstadoSesion,
    IntentoPruebaVida,
    Plataforma,
    SesionActivacion,
)
from src.domain.activacion_movil.repositories import ActivacionMovilRepository
from src.infrastructure.persistence.models import (
    DispositivoVinculadoModel,
    IntentoPruebaVidaModel,
    SesionActivacionModel,
)


class SqlAlchemyActivacionMovilRepository(ActivacionMovilRepository):
    """Repositorio transaccional; el caso de uso decide cuándo confirmar."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def dispositivo_esta_vinculado(
        self, cliente_id: UUID, installation_id: UUID
    ) -> bool:
        result = await self.session.execute(
            select(DispositivoVinculadoModel.id).where(
                DispositivoVinculadoModel.cliente_id == cliente_id,
                DispositivoVinculadoModel.installation_id == installation_id,
                DispositivoVinculadoModel.estado == "ACTIVO",
            )
        )
        return result.scalar_one_or_none() is not None

    async def obtener_sesion_creada(
        self, installation_id: UUID
    ) -> SesionActivacion | None:
        result = await self.session.execute(
            select(SesionActivacionModel)
            .where(
                SesionActivacionModel.installation_id == installation_id,
                SesionActivacionModel.estado == EstadoSesion.CREADA.value,
            )
            .order_by(SesionActivacionModel.creada_en.desc())
        )
        model = result.scalars().first()
        return self._a_sesion(model) if model else None

    async def guardar_sesion(self, sesion: SesionActivacion) -> None:
        self.session.add(
            SesionActivacionModel(
                id=sesion.id,
                cliente_id=sesion.cliente_id,
                installation_id=sesion.dispositivo.installation_id,
                plataforma=sesion.dispositivo.plataforma.value,
                modelo=sesion.dispositivo.modelo,
                version_so=sesion.dispositivo.version_so,
                tipo_captura=sesion.tipo_captura,
                estado=sesion.estado.value,
                creada_en=sesion.creada_en,
                expira_en=sesion.expira_en,
            )
        )
        await self.session.flush()

    async def cancelar_sesion(self, sesion_id: str) -> None:
        await self.session.execute(
            update(SesionActivacionModel)
            .where(
                SesionActivacionModel.id == sesion_id,
                SesionActivacionModel.estado == EstadoSesion.CREADA.value,
            )
            .values(estado=EstadoSesion.CANCELADA.value)
        )

    async def contar_intentos_consumidos(
        self, cliente_id: UUID, desde: datetime
    ) -> int:
        result = await self.session.execute(
            select(func.count(IntentoPruebaVidaModel.id)).where(
                IntentoPruebaVidaModel.cliente_id == cliente_id,
                IntentoPruebaVidaModel.creado_en >= desde,
                IntentoPruebaVidaModel.estado.in_(
                    [EstadoIntento.RECHAZADO.value, EstadoIntento.EN_CURSO.value]
                ),
            )
        )
        return result.scalar_one()

    async def guardar_intento(self, intento: IntentoPruebaVida) -> None:
        self.session.add(
            IntentoPruebaVidaModel(
                id=intento.id,
                cliente_id=intento.cliente_id,
                sesion_id=intento.sesion_id,
                installation_id=intento.installation_id,
                estado=intento.estado.value,
                folio=intento.folio,
                motivo=intento.motivo,
                creado_en=intento.creado_en,
                resuelto_en=intento.resuelto_en,
            )
        )
        await self.session.flush()

    async def actualizar_estado_intento(
        self,
        intento_id: UUID,
        estado: EstadoIntento,
        resuelto_en: datetime | None = None,
        folio: str | None = None,
        motivo: str | None = None,
    ) -> None:
        await self.session.execute(
            update(IntentoPruebaVidaModel)
            .where(IntentoPruebaVidaModel.id == intento_id)
            .values(
                estado=estado.value,
                resuelto_en=resuelto_en,
                folio=folio,
                motivo=motivo,
            )
        )

    @staticmethod
    def _a_sesion(model: SesionActivacionModel) -> SesionActivacion:
        return SesionActivacion(
            id=model.id,
            cliente_id=model.cliente_id,
            dispositivo=DatosDispositivo(
                installation_id=model.installation_id,
                plataforma=Plataforma(model.plataforma),
                modelo=model.modelo,
                version_so=model.version_so,
            ),
            tipo_captura=model.tipo_captura,
            estado=EstadoSesion(model.estado),
            creada_en=model.creada_en,
            expira_en=model.expira_en,
        )
