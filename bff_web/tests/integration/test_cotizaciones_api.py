import pytest
from httpx import ASGITransport, AsyncClient

from src.infrastructure.gateways.cotizacion_service_gateway import (
    CotizacionGatewayError,
)
from src.main import app
from src.presentation.dependencies import get_cotizacion_service_gateway


class FakeCotizacionGateway:
    def __init__(self):
        self.resultado = {"estado": "COTIZADA", "prima_mensual": 48046.25}
        self.error: tuple[int, str] | None = None
        self.payload: bytes | None = None

    async def cotizar(self, payload: bytes, content_type: str):
        self.payload = payload
        if self.error:
            raise CotizacionGatewayError(*self.error)
        return self.resultado


@pytest.fixture
async def bff_client():
    gateway = FakeCotizacionGateway()
    app.dependency_overrides[get_cotizacion_service_gateway] = lambda: gateway
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client, gateway
    app.dependency_overrides.clear()


async def test_cotizaciones_reenvia_solicitud_al_motor(bff_client):
    client, gateway = bff_client
    payload = b'{"ramo":"VIDA_HIPOTECARIO"}'

    response = await client.post(
        "/api/v1/bff-web/cotizaciones",
        content=payload,
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 200
    assert response.json()["prima_mensual"] == 48046.25
    assert gateway.payload == payload


async def test_cotizaciones_propaga_estado_funcional_del_motor(bff_client):
    client, gateway = bff_client
    gateway.error = (403, "CONSENTIMIENTO_NO_ACTIVO")

    response = await client.post(
        "/api/v1/bff-web/cotizaciones",
        json={"ramo": "VIDA_HIPOTECARIO"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "CONSENTIMIENTO_NO_ACTIVO"
