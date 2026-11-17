import httpx
import pytest

from src.infrastructure.gateways.identity_socios_gateway import (
    IdentitySociosGatewayError,
    IdentitySociosGateway,
)


async def test_reenvia_socio_y_actor_a_identity_service():
    async def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/identity-service/socios"
        assert request.headers["X-Actor-Id"] == "operator-123"
        assert request.headers["X-Correlation-Id"] == "corr-1"
        return httpx.Response(201, json={"id": "socio-1", "estado": "ACTIVO"})

    gateway = IdentitySociosGateway(
        base_url="http://identity.test", transport=httpx.MockTransport(handle)
    )
    try:
        response = await gateway.registrar_socio(
            {"nombre": "Banco Andino"}, "operator-123", "corr-1"
        )
    finally:
        await gateway.aclose()

    assert response == {"id": "socio-1", "estado": "ACTIVO"}


async def test_no_expone_detalles_del_servicio_en_error():
    async def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "fallo interno"})

    gateway = IdentitySociosGateway(
        base_url="http://identity.test", transport=httpx.MockTransport(handle)
    )
    try:
        with pytest.raises(IdentitySociosGatewayError) as error:
            await gateway.registrar_socio({"nombre": "Banco"}, "operator-123")
    finally:
        await gateway.aclose()

    assert error.value.status_code == 500
    assert error.value.detail == "fallo interno"
