from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.database import Base
from src.main import app, lifespan


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
