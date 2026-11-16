import asyncio
import os
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from src.core.database import Base
from src.application.ports.publicador_eventos import PublicacionEventoError, PublicadorEventos
from src.domain.eventos.entities import EventoOutbox
from src.infrastructure.messaging.outbox_relay import (
    _OUTBOX_ADVISORY_LOCK_KEY,
    OutboxRelay,
)
from src.infrastructure.persistence.evento_outbox_repository_impl import (
    SqlAlchemyEventoOutboxRepository,
)

DATABASE_URL = os.environ.get("PAYMENTS_OUTBOX_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="PAYMENTS_OUTBOX_TEST_DATABASE_URL no configurada"
)


@pytest.fixture
async def postgres_factory() -> AsyncGenerator[async_sessionmaker, None]:
    assert DATABASE_URL is not None
    schema = f"test_outbox_{uuid.uuid4().hex}"
    engine = create_async_engine(
        DATABASE_URL,
        execution_options={"schema_translate_map": {"payments": schema}},
    )
    creado = False
    try:
        async with engine.begin() as connection:
            await connection.execute(CreateSchema(schema))
            creado = True
            await connection.run_sync(Base.metadata.create_all)
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        try:
            if creado:
                async with engine.begin() as connection:
                    await connection.execute(DropSchema(schema, cascade=True, if_exists=True))
        finally:
            await engine.dispose()


async def crear_eventos(factory: async_sessionmaker, cantidad: int) -> list[EventoOutbox]:
    ahora = datetime.now(UTC)
    eventos = [
        EventoOutbox(
            tipo="PagoAprobado",
            agregado_id=uuid.uuid4(),
            payload={"numero": numero},
            creado_en=ahora + timedelta(seconds=numero),
        )
        for numero in range(cantidad)
    ]
    async with factory() as session:
        repo = SqlAlchemyEventoOutboxRepository(session)
        for evento in eventos:
            await repo.agregar(evento)
        await session.commit()
    return eventos


class PublicadorBloqueado(PublicadorEventos):
    def __init__(self) -> None:
        self.iniciado = asyncio.Event()
        self.liberar = asyncio.Event()
        self.publicados: list[dict] = []

    async def publicar(self, tipo: str, payload: dict) -> None:
        self.iniciado.set()
        await self.liberar.wait()
        self.publicados.append(payload)


class RelayObservado(OutboxRelay):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.intento_bloqueo = asyncio.Event()

    async def _adquirir_bloqueo(self, session: AsyncSession) -> None:
        self.intento_bloqueo.set()
        await super()._adquirir_bloqueo(session)


async def test_relays_comparten_bloqueo_y_publican_cada_evento_una_vez(postgres_factory):
    eventos = await crear_eventos(postgres_factory, 2)
    publicador = PublicadorBloqueado()
    primero = OutboxRelay(postgres_factory, publicador, 0.01, 2)
    segundo = RelayObservado(postgres_factory, publicador, 0.01, 2)
    tarea_primero = asyncio.create_task(primero.publicar_pendientes())
    tarea_segundo = None
    try:
        await asyncio.wait_for(publicador.iniciado.wait(), 5)
        async with postgres_factory() as session:
            resultado = await session.execute(
                text("SELECT pg_try_advisory_xact_lock(:lock_key)"),
                {"lock_key": _OUTBOX_ADVISORY_LOCK_KEY},
            )
            assert resultado.scalar_one() is False

        tarea_segundo = asyncio.create_task(segundo.publicar_pendientes())
        await asyncio.wait_for(segundo.intento_bloqueo.wait(), 5)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(tarea_segundo), 0.1)
        assert publicador.publicados == []

        publicador.liberar.set()
        cantidades = await asyncio.wait_for(asyncio.gather(tarea_primero, tarea_segundo), 5)
        assert sum(cantidades) == 2
        assert publicador.publicados == [evento.payload for evento in eventos]
        async with postgres_factory() as session:
            assert await SqlAlchemyEventoOutboxRepository(session).obtener_pendientes(10) == []
    finally:
        publicador.liberar.set()
        tareas = [tarea_primero]
        if tarea_segundo is not None:
            tareas.append(tarea_segundo)
        for tarea in tareas:
            if not tarea.done():
                tarea.cancel()
        await asyncio.gather(*tareas, return_exceptions=True)


async def test_cancelacion_libera_el_bloqueo_y_permita_reintentar(postgres_factory):
    (evento,) = await crear_eventos(postgres_factory, 1)
    publicador = PublicadorBloqueado()
    relay = OutboxRelay(postgres_factory, publicador, 0.01, 1)
    tarea = asyncio.create_task(relay.publicar_pendientes())
    try:
        await asyncio.wait_for(publicador.iniciado.wait(), 5)
        tarea.cancel()
        with pytest.raises(asyncio.CancelledError):
            await tarea

        publicador.liberar.set()
        assert await asyncio.wait_for(relay.publicar_pendientes(), 5) == 1
        assert publicador.publicados == [evento.payload]
    finally:
        if not tarea.done():
            tarea.cancel()
        await asyncio.gather(tarea, return_exceptions=True)


async def test_fallo_de_publicacion_libera_el_bloqueo_y_permita_reintentar(postgres_factory):
    (evento,) = await crear_eventos(postgres_factory, 1)

    class PublicadorConFallo(PublicadorBloqueado):
        async def publicar(self, tipo: str, payload: dict) -> None:
            raise PublicacionEventoError("SQS no disponible")

    fallido = OutboxRelay(postgres_factory, PublicadorConFallo(), 0.01, 1)
    assert await asyncio.wait_for(fallido.publicar_pendientes(), 5) == 0

    async with postgres_factory() as session:
        (pendiente,) = await SqlAlchemyEventoOutboxRepository(session).obtener_pendientes(1)
        assert pendiente.evento_id == evento.evento_id
        assert pendiente.intentos == 1
        assert pendiente.ultimo_error == "SQS no disponible"

    publicador = PublicadorBloqueado()
    publicador.liberar.set()
    reintento = OutboxRelay(postgres_factory, publicador, 0.01, 1)
    assert await asyncio.wait_for(reintento.publicar_pendientes(), 5) == 1
    assert publicador.publicados == [evento.payload]
