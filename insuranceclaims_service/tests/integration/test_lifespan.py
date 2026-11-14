from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.database import Base
from src.main import app, lifespan


@pytest.fixture(autouse=True)
def sin_semilla(monkeypatch):
    monkeypatch.setattr("src.main.settings.SEED_ON_STARTUP", False)


async def test_siembra_el_catalogo_al_arrancar(monkeypatch):
    connection = MagicMock()
    connection.execute = AsyncMock()
    connection.run_sync = AsyncMock()
    engine = MagicMock()
    engine.begin.return_value.__aenter__ = AsyncMock(return_value=connection)
    engine.begin.return_value.__aexit__ = AsyncMock(return_value=False)
    engine.dispose = AsyncMock()
    sembrar = AsyncMock()
    monkeypatch.setattr("src.main.engine", engine)
    monkeypatch.setattr("src.main._sembrar_catalogo", sembrar)
    monkeypatch.setattr("src.main.settings.SEED_ON_STARTUP", True)

    async with lifespan(app):
        sembrar.assert_awaited_once()


async def test_falla_de_la_semilla_no_impide_arrancar(monkeypatch):
    from src.main import _sembrar_catalogo

    def sesion_que_falla():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr("src.main.SessionLocal", sesion_que_falla)

    await _sembrar_catalogo()


async def test_crea_esquema_y_tablas(monkeypatch):
    connection = MagicMock()
    connection.execute = AsyncMock()
    connection.run_sync = AsyncMock()
    engine = MagicMock()
    engine.begin.return_value.__aenter__ = AsyncMock(return_value=connection)
    engine.begin.return_value.__aexit__ = AsyncMock(return_value=False)
    engine.dispose = AsyncMock()
    monkeypatch.setattr("src.main.engine", engine)

    async with lifespan(app):
        assert str(connection.execute.await_args.args[0]) == "CREATE SCHEMA IF NOT EXISTS insuranceclaims"
        connection.run_sync.assert_awaited_once_with(Base.metadata.create_all)
    engine.dispose.assert_awaited_once()


async def test_error_de_base_de_datos_impide_arranque(monkeypatch):
    engine = MagicMock()
    engine.begin.return_value.__aenter__ = AsyncMock(side_effect=RuntimeError("database unavailable"))
    engine.begin.return_value.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr("src.main.engine", engine)

    with pytest.raises(RuntimeError, match="database unavailable"):
        async with lifespan(app):
            pytest.fail("el servicio no debe arrancar")
