import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import Base
from src.main import app, lifespan


def _engine_falso() -> MagicMock:
    connection = MagicMock()
    connection.execute = AsyncMock()
    connection.run_sync = AsyncMock()
    engine = MagicMock()
    engine.begin.return_value.__aenter__ = AsyncMock(return_value=connection)
    engine.begin.return_value.__aexit__ = AsyncMock(return_value=False)
    engine.dispose = AsyncMock()
    return engine


async def test_crea_esquema_y_tablas(monkeypatch):
    monkeypatch.setattr("src.main.settings.PAGO_APROBADO_QUEUE_URL", "")
    connection = MagicMock()
    connection.execute = AsyncMock()
    connection.run_sync = AsyncMock()
    engine = MagicMock()
    engine.begin.return_value.__aenter__ = AsyncMock(return_value=connection)
    engine.begin.return_value.__aexit__ = AsyncMock(return_value=False)
    engine.dispose = AsyncMock()
    monkeypatch.setattr("src.main.engine", engine)

    async with lifespan(app):
        assert str(connection.execute.await_args.args[0]) == "CREATE SCHEMA IF NOT EXISTS payments"
        connection.run_sync.assert_awaited_once_with(Base.metadata.create_all)
    engine.dispose.assert_awaited_once()


async def test_create_all_no_crea_ni_elimina_tabla_pago_existente(db_session: AsyncSession):
    connection = await db_session.connection()
    result = await connection.execute(
        text("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'pago'")
    )
    assert result.scalar_one_or_none() is None

    await connection.execute(text("CREATE TABLE pago (id INTEGER PRIMARY KEY)"))
    await connection.execute(text("INSERT INTO pago (id) VALUES (1)"))
    await connection.run_sync(Base.metadata.create_all)

    result = await connection.execute(text("SELECT id FROM pago"))
    assert result.scalar_one() == 1


async def test_sin_cola_configurada_no_inicia_el_relay(monkeypatch):
    monkeypatch.setattr("src.main.settings.PAGO_APROBADO_QUEUE_URL", "")
    monkeypatch.setattr("src.main.engine", _engine_falso())
    relay = MagicMock()
    monkeypatch.setattr("src.main.OutboxRelay", relay)

    async with lifespan(app):
        pass

    relay.assert_not_called()


async def test_con_cola_configurada_inicia_y_detiene_el_relay(monkeypatch):
    monkeypatch.setattr("src.main.settings.PAGO_APROBADO_QUEUE_URL", "http://localstack:4566/000000000000/q")
    monkeypatch.setattr("src.main.engine", _engine_falso())
    monkeypatch.setattr("src.main.SqsPublicadorEventos", MagicMock())
    iniciado, cancelado = asyncio.Event(), asyncio.Event()

    class RelayFalso:
        def __init__(self, session_factory, publicador, intervalo, lote):
            self.args = (intervalo, lote)

        async def ejecutar(self):
            iniciado.set()
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                cancelado.set()
                raise

    monkeypatch.setattr("src.main.OutboxRelay", RelayFalso)

    async with lifespan(app):
        await asyncio.wait_for(iniciado.wait(), 1)
        assert not cancelado.is_set()

    assert cancelado.is_set()


async def test_error_de_base_de_datos_impide_arranque(monkeypatch):
    engine = MagicMock()
    engine.begin.return_value.__aenter__ = AsyncMock(side_effect=RuntimeError("database unavailable"))
    engine.begin.return_value.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr("src.main.engine", engine)

    with pytest.raises(RuntimeError, match="database unavailable"):
        async with lifespan(app):
            pytest.fail("el servicio no debe arrancar")
