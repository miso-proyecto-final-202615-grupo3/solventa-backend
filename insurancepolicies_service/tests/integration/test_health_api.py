import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from src import main


async def test_health_check(async_client: AsyncClient):
    response = await async_client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data


async def test_readiness_requiere_esquema_listo(async_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(async_client._transport.app.state, "schema_ready", False, raising=False)
    response = await async_client.get("/ready")

    assert response.status_code == 503


async def test_root(async_client: AsyncClient):
    response = await async_client.get("/")

    assert response.status_code == 200
    assert "Insurance Policies" in response.json()["message"]


async def test_no_expone_otros_endpoints(async_client: AsyncClient):
    response = await async_client.get("/api/v1/insurancepolicies-service/polizas")

    assert response.status_code == 404


@pytest.mark.parametrize("fallo_bd", [False, True])
async def test_lifespan_crea_esquema_y_detiene_procesos(monkeypatch, caplog, fallo_bd):
    conexion = MagicMock()
    conexion.execute = AsyncMock(side_effect=RuntimeError("BD no disponible") if fallo_bd else None)
    conexion.run_sync = AsyncMock()
    contexto = MagicMock()
    contexto.__aenter__ = AsyncMock(return_value=conexion)
    contexto.__aexit__ = AsyncMock(return_value=False)
    engine = MagicMock()
    engine.begin.return_value = contexto
    detenido = asyncio.Event()

    async def proceso():
        try:
            await asyncio.Event().wait()
        finally:
            detenido.set()

    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "crear_procesos", lambda: {"prueba": proceso()})

    if fallo_bd:
        with pytest.raises(RuntimeError, match="BD no disponible"):
            async with main.lifespan(main.app):
                pass
        assert not detenido.is_set()
    else:
        async with main.lifespan(main.app):
            await asyncio.sleep(0)
            assert not detenido.is_set()

    if not fallo_bd:
        assert detenido.is_set()
    engine.begin.assert_called_once_with()
    conexion.execute.assert_awaited_once()
    assert str(conexion.execute.await_args.args[0]) == "CREATE SCHEMA IF NOT EXISTS insurancepolicies"
    if fallo_bd:
        conexion.run_sync.assert_not_awaited()
    else:
        conexion.run_sync.assert_awaited_once_with(main.Base.metadata.create_all)
