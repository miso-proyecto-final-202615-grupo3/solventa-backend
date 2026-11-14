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
