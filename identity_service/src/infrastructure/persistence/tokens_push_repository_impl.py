import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.tokens_push import DestinoPush
from src.infrastructure.persistence.models import DispositivoVinculadoModel

ACTIVO = "ACTIVO"
_SIN_TOKEN = {"push_token": None, "push_plataforma": None, "push_actualizado_en": None}


class SqlAlchemyTokensPushRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def asignar_a_dispositivo_activo(
        self, cliente_id: uuid.UUID, installation_id: uuid.UUID, token: str, plataforma: str, ahora: datetime
    ) -> bool:
        dispositivo = await self._session.scalar(
            select(DispositivoVinculadoModel).where(
                DispositivoVinculadoModel.cliente_id == cliente_id,
                DispositivoVinculadoModel.installation_id == installation_id,
                DispositivoVinculadoModel.estado == ACTIVO,
            )
        )
        if dispositivo is None:
            return False
        # CA3: un token solo pertenece a un dispositivo; si estaba en otro (otro cliente o una vinculación vieja), se quita.
        await self._session.execute(
            update(DispositivoVinculadoModel)
            .where(DispositivoVinculadoModel.push_token == token, DispositivoVinculadoModel.id != dispositivo.id)
            .values(**_SIN_TOKEN)
        )
        dispositivo.push_token = token
        dispositivo.push_plataforma = plataforma
        dispositivo.push_actualizado_en = ahora
        await self._session.commit()
        return True

    async def quitar_de_dispositivo(self, cliente_id: uuid.UUID, installation_id: uuid.UUID) -> None:
        await self._session.execute(
            update(DispositivoVinculadoModel)
            .where(
                DispositivoVinculadoModel.cliente_id == cliente_id,
                DispositivoVinculadoModel.installation_id == installation_id,
            )
            .values(**_SIN_TOKEN)
        )
        await self._session.commit()

    async def quitar_token(self, token: str) -> None:
        await self._session.execute(
            update(DispositivoVinculadoModel).where(DispositivoVinculadoModel.push_token == token).values(**_SIN_TOKEN)
        )
        await self._session.commit()

    async def destinos_de_cliente(self, cliente_id: uuid.UUID) -> list[DestinoPush]:
        filas = await self._session.scalars(
            select(DispositivoVinculadoModel).where(
                DispositivoVinculadoModel.cliente_id == cliente_id,
                DispositivoVinculadoModel.estado == ACTIVO,
                DispositivoVinculadoModel.push_token.is_not(None),
            )
        )
        return [DestinoPush(d.installation_id, d.push_token, d.push_plataforma or "ANDROID") for d in filas.all()]
