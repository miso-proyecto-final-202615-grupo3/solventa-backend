from unittest.mock import AsyncMock, MagicMock

import pytest

import src.main as main


def _session_factory():
    session = MagicMock()
    session.execute = AsyncMock()
    connection = MagicMock()
    connection.run_sync = AsyncMock()
    session.connection = AsyncMock(return_value=connection)
    factory = MagicMock()
    transaction = factory.begin.return_value
    transaction.__aenter__ = AsyncMock(return_value=session)
    transaction.__aexit__ = AsyncMock(return_value=False)
    return factory, session, connection, transaction


async def test_lifespan_inicializa_en_una_transaccion(monkeypatch):
    factory, session, connection, transaction = _session_factory()

    async def verificar_seed(session_actual):
        assert session_actual is session
        assert [c[0] for c in session.method_calls] == ["execute", "execute", "connection"]
        connection.run_sync.assert_awaited_once_with(main.Base.metadata.create_all)
        transaction.__aexit__.assert_not_awaited()

    async def verificar_inicio(app):
        transaction.__aexit__.assert_awaited_once_with(None, None, None)

    seed = AsyncMock(side_effect=verificar_seed)
    iniciar = AsyncMock(side_effect=verificar_inicio)
    cerrar = AsyncMock()
    monkeypatch.setattr(main, "SessionLocal", factory)
    monkeypatch.setattr(main, "sembrar_catalogo", seed)
    monkeypatch.setattr(main, "inicializar_recursos", iniciar)
    monkeypatch.setattr(main, "cerrar_recursos", cerrar)
    monkeypatch.setattr(main.settings, "SEED_ON_STARTUP", True)

    async with main.lifespan(main.FastAPI()):
        assert [str(c.args[0]) for c in session.execute.await_args_list] == [
            "SELECT pg_advisory_xact_lock(1397705812, 2)",
            "CREATE SCHEMA IF NOT EXISTS quotingengine",
        ]
        connection.run_sync.assert_awaited_once_with(main.Base.metadata.create_all)
        seed.assert_awaited_once_with(session)
        transaction.__aexit__.assert_awaited_once_with(None, None, None)
        iniciar.assert_awaited_once()

    cerrar.assert_awaited_once_with()


async def test_lifespan_omite_seed_si_esta_deshabilitado(monkeypatch):
    factory, _, _, _ = _session_factory()
    seed = AsyncMock()
    monkeypatch.setattr(main, "SessionLocal", factory)
    monkeypatch.setattr(main, "sembrar_catalogo", seed)
    monkeypatch.setattr(main, "inicializar_recursos", AsyncMock())
    monkeypatch.setattr(main, "cerrar_recursos", AsyncMock())
    monkeypatch.setattr(main.settings, "SEED_ON_STARTUP", False)

    async with main.lifespan(main.FastAPI()):
        pass

    seed.assert_not_awaited()


@pytest.mark.parametrize("operation", ["lock", "schema", "tables", "seed"])
async def test_error_de_inicializacion_impide_arranque_y_revierte(monkeypatch, operation):
    factory, session, connection, transaction = _session_factory()
    error = RuntimeError(f"fallo en {operation}")
    if operation == "lock":
        session.execute.side_effect = error
    elif operation == "schema":
        session.execute.side_effect = [None, error]
    elif operation == "tables":
        connection.run_sync.side_effect = error
    seed = AsyncMock(side_effect=error if operation == "seed" else None)
    iniciar = AsyncMock()
    monkeypatch.setattr(main, "SessionLocal", factory)
    monkeypatch.setattr(main, "sembrar_catalogo", seed)
    monkeypatch.setattr(main, "inicializar_recursos", iniciar)
    monkeypatch.setattr(main.settings, "SEED_ON_STARTUP", True)

    with pytest.raises(RuntimeError, match=f"fallo en {operation}"):
        async with main.lifespan(main.FastAPI()):
            pytest.fail("el servicio no debe arrancar")

    assert transaction.__aexit__.await_args.args[:2] == (RuntimeError, error)
    iniciar.assert_not_awaited()
