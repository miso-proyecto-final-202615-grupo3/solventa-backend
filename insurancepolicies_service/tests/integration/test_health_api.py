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


async def test_root(async_client: AsyncClient):
    response = await async_client.get("/")

    assert response.status_code == 200
    assert "Insurance Policies" in response.json()["message"]


async def test_no_expone_otros_endpoints(async_client: AsyncClient):
    response = await async_client.get("/api/v1/insurancepolicies-service/polizas")

    assert response.status_code == 404


async def test_lifespan_crea_esquema_y_detiene_procesos(monkeypatch):
    conexion = MagicMock()
    conexion.execute = AsyncMock()
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

    def crear_procesos():
        contexto.__aexit__.assert_awaited_once_with(None, None, None)
        return {"prueba": proceso()}

    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "crear_procesos", crear_procesos)

    async with main.lifespan(main.app):
        await asyncio.sleep(0)
        assert not detenido.is_set()

    assert detenido.is_set()
    engine.begin.assert_called_once_with()
    assert [str(call.args[0]) for call in conexion.execute.await_args_list] == [
        "SELECT pg_advisory_xact_lock(1397705812, 3)",
        "CREATE SCHEMA IF NOT EXISTS insurancepolicies",
    ]
    assert [call[0] for call in conexion.method_calls] == ["execute", "execute", "run_sync"]
    conexion.run_sync.assert_awaited_once_with(main.Base.metadata.create_all)


@pytest.mark.parametrize("etapa", ["bloqueo", "esquema", "tablas"])
async def test_lifespan_falla_y_no_inicia_procesos_si_falla_bd(monkeypatch, etapa):
    error = RuntimeError("BD no disponible")
    conexion = MagicMock()
    conexion.execute = AsyncMock()
    conexion.run_sync = AsyncMock()
    if etapa == "bloqueo":
        conexion.execute.side_effect = error
    elif etapa == "esquema":
        conexion.execute.side_effect = [None, error]
    else:
        conexion.run_sync.side_effect = error
    contexto = MagicMock()
    contexto.__aenter__ = AsyncMock(return_value=conexion)
    contexto.__aexit__ = AsyncMock(return_value=False)
    engine = MagicMock()
    engine.begin.return_value = contexto
    crear_procesos = MagicMock()
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "crear_procesos", crear_procesos)

    with pytest.raises(RuntimeError, match="BD no disponible"):
        async with main.lifespan(main.app):
            pytest.fail("el servicio no debe arrancar")

    engine.begin.assert_called_once_with()
    contexto.__aexit__.assert_awaited_once()
    assert contexto.__aexit__.await_args.args[:2] == (RuntimeError, error)
    crear_procesos.assert_not_called()
    instrucciones = [str(call.args[0]) for call in conexion.execute.await_args_list]
    assert instrucciones[0] == "SELECT pg_advisory_xact_lock(1397705812, 3)"
    if etapa == "bloqueo":
        assert len(instrucciones) == 1
    else:
        assert instrucciones[1:] == ["CREATE SCHEMA IF NOT EXISTS insurancepolicies"]
    if etapa != "tablas":
        conexion.run_sync.assert_not_awaited()
    else:
        conexion.run_sync.assert_awaited_once_with(main.Base.metadata.create_all)
