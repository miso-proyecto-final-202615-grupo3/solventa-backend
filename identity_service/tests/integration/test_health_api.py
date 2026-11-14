from httpx import AsyncClient


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
    assert "Identity" in response.json()["message"]
