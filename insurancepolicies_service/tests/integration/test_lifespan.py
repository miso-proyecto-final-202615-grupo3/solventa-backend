from unittest.mock import AsyncMock, MagicMock

import pytest

import src.main as main


async def test_lifespan_bloquea_antes_de_crear_esquema(monkeypatch):
    connection = MagicMock()
    connection.execute = AsyncMock()
    connection.run_sync = AsyncMock()
    engine = MagicMock()
    engine.begin.return_value.__aenter__ = AsyncMock(return_value=connection)
    engine.begin.return_value.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "crear_procesos", lambda: {})
    monkeypatch.setattr(main, "detener_procesos", AsyncMock())

    async with main.lifespan(main.app):
        assert [str(c.args[0]) for c in connection.execute.await_args_list] == [
            "SELECT pg_advisory_xact_lock(1397705812, 3)",
            "CREATE SCHEMA IF NOT EXISTS insurancepolicies",
        ]
        assert [c[0] for c in connection.method_calls] == ["execute", "execute", "run_sync"]
        connection.run_sync.assert_awaited_once_with(main.Base.metadata.create_all)


async def test_error_de_base_de_datos_impide_arranque(monkeypatch):
    engine = MagicMock()
    engine.begin.return_value.__aenter__ = AsyncMock(
        side_effect=RuntimeError("database unavailable")
    )
    engine.begin.return_value.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(main, "engine", engine)
    procesos = MagicMock()
    monkeypatch.setattr(main, "crear_procesos", procesos)

    with pytest.raises(RuntimeError, match="database unavailable"):
        async with main.lifespan(main.app):
            pytest.fail("el servicio no debe arrancar")
    procesos.assert_not_called()
