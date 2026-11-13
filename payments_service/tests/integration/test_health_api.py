from httpx import AsyncClient


async def test_health_check(async_client: AsyncClient):
    response = await async_client.get("/health", headers={"X-Correlation-Id": "test-123"})
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "version": "0.1.0"}
    assert response.headers["X-Correlation-Id"] == "test-123"


async def test_root(async_client: AsyncClient):
    response = await async_client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Solventa Payments Service"}


async def test_metricas(async_client: AsyncClient):
    await async_client.get("/health")
    response = await async_client.get("/metrics")
    assert response.status_code == 200
    assert "http_requests_total" in response.text


async def test_docs_y_endpoints_de_pago_de_prima(async_client: AsyncClient):
    schema = await async_client.get("/openapi.json")
    assert schema.status_code == 200
    prefijo = "/api/v1/payments-service"
    assert set(schema.json()["paths"]) == {
        "/",
        "/health",
        "/metrics",
        f"{prefijo}/cotizaciones/{{cotizacion_id}}/resumen-pago",
        f"{prefijo}/pagos",
        f"{prefijo}/pagos/{{pago_id}}",
    }
    assert (await async_client.get("/docs")).status_code == 200
    assert (await async_client.get("/redoc")).status_code == 200
