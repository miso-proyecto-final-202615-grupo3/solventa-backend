from unittest.mock import AsyncMock, MagicMock

import pytest

import src.main as main


class _EngineSinBD:
    def begin(self):
        raise RuntimeError("base de datos no disponible")


class _ContextoBD:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        return False

    async def execute(self, statement):
        return None

    async def run_sync(self, callback):
        return None


class _EngineConBD:
    def begin(self):
        return _ContextoBD()


async def test_lifespan_falla_por_falta_de_bd(monkeypatch):
    monkeypatch.setattr(main, "engine", _EngineSinBD())
    monkeypatch.setattr(main.settings, "GRPC_PORT", 0)

    with pytest.raises(RuntimeError, match="base de datos no disponible"):
        async with main.lifespan(None):
            pass


async def test_lifespan_inicia_y_detiene_servidor_grpc(monkeypatch):
    eventos = []

    class ServidorFalso:
        async def stop(self, grace):
            eventos.append("stop")

    async def iniciar(factory, open_finance_gateway, port):
        eventos.append(("start", port))
        return ServidorFalso()

    monkeypatch.setattr(main, "engine", _EngineConBD())
    monkeypatch.setattr(main, "iniciar_servidor_grpc", iniciar)
    monkeypatch.setattr(main.settings, "GRPC_ENABLED", True)
    monkeypatch.setattr(main.settings, "GRPC_PORT", 50999)

    async with main.lifespan(None):
        assert eventos == [("start", 50999)]

    assert eventos[-1] == "stop"


async def test_lifespan_bloquea_antes_de_crear_esquema(monkeypatch):
    connection = MagicMock()
    connection.execute = AsyncMock()
    connection.run_sync = AsyncMock()
    engine = MagicMock()
    engine.begin.return_value.__aenter__ = AsyncMock(return_value=connection)
    engine.begin.return_value.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main.settings, "GRPC_ENABLED", False)
    monkeypatch.setattr(main, "cerrar_consentimiento_cache", AsyncMock())

    async with main.lifespan(None):
        assert [str(c.args[0]) for c in connection.execute.await_args_list] == [
            "SELECT pg_advisory_xact_lock(1397705812, 1)",
            "CREATE SCHEMA IF NOT EXISTS identity",
        ]
        assert [c[0] for c in connection.method_calls] == ["execute", "execute", "run_sync"]
        connection.run_sync.assert_awaited_once_with(main.Base.metadata.create_all)
