"""HU4.2.2 · Relay del outbox: orden, reintentos y FALLIDO (N3)."""
import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.core.database import Base
from src.domain.siniestros.entities import EventoOutbox, Siniestro
from src.infrastructure.messaging.outbox_relay import OutboxRelay
from src.infrastructure.persistence.models import EventoOutboxModel
from src.infrastructure.persistence.siniestros_repository_impl import (
    SqlAlchemyEventoOutboxRepository,
    SqlAlchemySiniestroRepository,
)
from tests.fakes import AHORA, CLIENTE


@pytest.fixture
async def factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False},
        execution_options={"schema_translate_map": {"insuranceclaims": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


class NotificarFalso:
    def __init__(self, fallos: int = 0) -> None:
        self.fallos = fallos
        self.procesados: list[str] = []

    async def ejecutar(self, evento, siniestro):
        if self.fallos:
            self.fallos -= 1
            raise RuntimeError("FCM no respondió")
        self.procesados.append(evento.payload["estado"])
        return 1


async def _sembrar(factory, estados: list[str]) -> list[uuid.UUID]:
    ids = []
    async with factory() as session:
        siniestro = Siniestro(
            poliza_id=uuid.uuid4(), tipo="ROBO", estado="REPORTADO", clave_idempotencia=str(uuid.uuid4()),
            ocurrido_en=AHORA, reportado_en=AHORA, cliente_id=CLIENTE, numero="SIN-2026-RELAY001",
        )
        await SqlAlchemySiniestroRepository(session).guardar(siniestro)
        outbox = SqlAlchemyEventoOutboxRepository(session)
        for indice, estado in enumerate(estados):
            evento = EventoOutbox(
                tipo="SINIESTRO_ESTADO", agregado_id=siniestro.siniestro_id, payload={"estado": estado},
                creado_en=AHORA.replace(second=indice),
            )
            await outbox.guardar(evento)
            ids.append(evento.evento_id)
        await session.commit()
    return ids


async def _estado(factory, evento_id) -> EventoOutboxModel:
    async with factory() as session:
        return await session.get(EventoOutboxModel, evento_id)


async def test_publica_en_orden_de_creacion(factory):
    ids = await _sembrar(factory, ["EN_EVALUACION", "APROBADO"])
    notificar = NotificarFalso()

    publicados = await OutboxRelay(factory, notificar, 0.01, 5).publicar_pendientes()

    assert publicados == 2
    assert notificar.procesados == ["EN_EVALUACION", "APROBADO"]
    assert {(await _estado(factory, i)).estado for i in ids} == {"PUBLICADO"}


async def test_un_fallo_detiene_el_lote_y_se_reintenta(factory):
    ids = await _sembrar(factory, ["EN_EVALUACION", "APROBADO"])
    notificar = NotificarFalso(fallos=1)
    relay = OutboxRelay(factory, notificar, 0.01, 5)

    primero = await relay.publicar_pendientes()
    fallido = await _estado(factory, ids[0])
    segundo = await relay.publicar_pendientes()

    assert primero == 0
    assert (fallido.estado, fallido.intentos) == ("PENDIENTE", 1)
    assert "FCM no respondió" in fallido.ultimo_error
    assert segundo == 2


async def test_queda_fallido_tras_el_maximo_de_intentos(factory):
    ids = await _sembrar(factory, ["EN_EVALUACION"])
    relay = OutboxRelay(factory, NotificarFalso(fallos=10), 0.01, 3)

    for _ in range(3):
        await relay.publicar_pendientes()

    evento = await _estado(factory, ids[0])
    assert (evento.estado, evento.intentos) == ("FALLIDO", 3)
    assert await relay.publicar_pendientes() == 0  # ya no se reintenta
