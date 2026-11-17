import httpx
import pytest

from src.infrastructure.gateways.partners_service_gateway import (
    PartnersGatewayError,
    PartnersServiceGateway,
)


async def test_reenvia_socio_y_actor_por_canal_interno():
    async def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/partners-service/socios"
        assert request.headers["X-Partners-Internal-Token"] == "internal-secret"
        assert request.headers["X-Actor-Id"] == "operator-123"
        assert request.headers["X-Correlation-Id"] == "corr-1"
        assert request.read() == b'{"nombre":"Banco Andino"}'
        return httpx.Response(201, json={"id": "socio-1", "estado": "PENDIENTE"})

    gateway = PartnersServiceGateway(
        base_url="http://partners.test",
        internal_token="internal-secret",
        transport=httpx.MockTransport(handle),
    )
    try:
        response = await gateway.registrar_socio(
            {"nombre": "Banco Andino"}, "operator-123", "corr-1"
        )
    finally:
        await gateway.aclose()

    assert response == {"id": "socio-1", "estado": "PENDIENTE"}


async def test_falla_cerrado_si_falta_secreto_interno():
    gateway = PartnersServiceGateway(
        base_url="http://partners.test",
        internal_token="",
        transport=httpx.MockTransport(lambda request: httpx.Response(201)),
    )
    try:
        with pytest.raises(PartnersGatewayError) as error:
            await gateway.registrar_socio({"nombre": "Banco"}, "operator-123")
    finally:
        await gateway.aclose()

    assert error.value.status_code == 503


async def test_no_expone_el_token_interno_en_error_del_servicio():
    async def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "fallo interno"})

    gateway = PartnersServiceGateway(
        base_url="http://partners.test",
        internal_token="internal-secret",
        transport=httpx.MockTransport(handle),
    )
    try:
        with pytest.raises(PartnersGatewayError) as error:
            await gateway.registrar_socio({"nombre": "Banco"}, "operator-123")
    finally:
        await gateway.aclose()

    assert error.value.status_code == 500
    assert "internal-secret" not in str(error.value.detail)
