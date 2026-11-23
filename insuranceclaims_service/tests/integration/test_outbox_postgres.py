"""HU4.2.2 · Dos relays a la vez contra Postgres real no envían el mismo evento dos veces (bloqueo advisory).

Se salta sin `TEST_POSTGRES_URL` (dentro de la red de compose:
`postgresql+asyncpg://postgres:postgres@db:5432/identity_db`).
"""
import asyncio
import os
import uuid

import pytest
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.core.database import Base
from src.domain.siniestros.entities import EventoOutbox, Siniestro
from src.infrastructure.messaging.outbox_relay import OutboxRelay
from src.infrastructure.persistence.models import EventoOutboxModel, SiniestroModel
from src.infrastructure.persistence.siniestros_repository_impl import (
    SqlAlchemyEventoOutboxRepository,
    SqlAlchemySiniestroRepository,
)
from tests.fakes import AHORA, CLIENTE

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")
pytestmark = [pytest.mark.postgres, pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL no está definida")]


class NotificarLento:
    def __init__(self) -> None:
        self.procesados: list[uuid.UUID] = []

    async def ejecutar(self, evento, siniestro):
        await asyncio.sleep(0.05)
        self.procesados.append(evento.evento_id)
        return 1


async def test_dos_relays_concurrentes_procesan_cada_evento_una_sola_vez():
    engine = create_async_engine(POSTGRES_URL)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS insuranceclaims"))
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    numero = f"SIN-T-{uuid.uuid4().hex[:8]}"
    async with factory() as session:
        siniestro = Siniestro(
            poliza_id=uuid.uuid4(), tipo="ROBO", estado="REPORTADO", clave_idempotencia=str(uuid.uuid4()),
            ocurrido_en=AHORA, reportado_en=AHORA, cliente_id=CLIENTE, numero=numero, canal="MOVIL",
            producto_codigo="PROTECCION_DISPOSITIVOS",
        )
        await SqlAlchemySiniestroRepository(session).guardar(siniestro)
        for _ in range(6):
            await SqlAlchemyEventoOutboxRepository(session).guardar(
                EventoOutbox(tipo="SINIESTRO_ESTADO", agregado_id=siniestro.siniestro_id, payload={"estado": "X"})
            )
        await session.commit()

    notificar = NotificarLento()
    try:
        await asyncio.gather(
            OutboxRelay(factory, notificar, 0.01, 5).publicar_pendientes(),
            OutboxRelay(factory, notificar, 0.01, 5).publicar_pendientes(),
        )
        assert len(notificar.procesados) == 6
        assert len(set(notificar.procesados)) == 6
    finally:
        async with factory() as session:
            await session.execute(delete(EventoOutboxModel).where(EventoOutboxModel.agregado_id == siniestro.siniestro_id))
            await session.execute(delete(SiniestroModel).where(SiniestroModel.siniestro_id == siniestro.siniestro_id))
            await session.commit()
        await engine.dispose()
