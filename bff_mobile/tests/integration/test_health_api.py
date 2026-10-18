from httpx import AsyncClient


async def test_health_check(async_client: AsyncClient):
    response = await async_client.get("/api/v1/bff-mobile/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data


async def test_root(async_client: AsyncClient):
    response = await async_client.get("/")

    assert response.status_code == 200
    assert "BFF Mobile" in response.json()["message"]
