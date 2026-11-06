from httpx import AsyncClient


async def test_health_check(async_client: AsyncClient):
    response = await async_client.get("/health", headers={"X-Correlation-Id": "test-123"})
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "version": "0.1.0"}
    assert response.headers["X-Correlation-Id"] == "test-123"


async def test_root(async_client: AsyncClient):
    response = await async_client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Solventa Insurance Claims Service"}


async def test_docs_y_openapi(async_client: AsyncClient):
    docs = await async_client.get("/docs")
    assert docs.status_code == 200
    assert "/openapi.json" in docs.text
    assert (await async_client.get("/redoc")).status_code == 200

    schema = await async_client.get("/openapi.json")
    assert schema.status_code == 200
    assert set(schema.json()["paths"]) == {"/", "/health", "/metrics"}


async def test_no_expone_otros_endpoints(async_client: AsyncClient):
    for path in ("/api/v1/insuranceclaims-service/siniestros",):
        assert (await async_client.get(path)).status_code == 404


async def test_metricas(async_client: AsyncClient):
    await async_client.get("/health")
    response = await async_client.get("/metrics")
    assert response.status_code == 200
    assert "http_requests_total" in response.text
