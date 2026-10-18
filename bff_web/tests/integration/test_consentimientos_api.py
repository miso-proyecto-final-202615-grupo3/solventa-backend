import pytest
from httpx import ASGITransport, AsyncClient

from src.infrastructure.gateways.identity_service_gateway import (
    IdentityGatewayError,
)
from src.main import app
from src.presentation.dependencies import get_identity_service_gateway

AUDITORIA = {
    "cliente": {"id": "uuid", "correo": "ana@example.com"},
    "eventos": [{"tipo_accion": "ACEPTACION", "canal": "web"}],
}


class FakeIdentityGateway:
    def __init__(self):
        self.params: dict[str, str] | None = None
        self.error: tuple[int, str] | None = None

    async def consultar_auditoria_consentimiento(self, params: dict[str, str]) -> dict:
        if self.error is not None:
            raise IdentityGatewayError(*self.error)
        self.params = params
        return AUDITORIA


@pytest.fixture
def fake_gateway() -> FakeIdentityGateway:
    return FakeIdentityGateway()


@pytest.fixture
async def bff_client(fake_gateway: FakeIdentityGateway):
    app.dependency_overrides[get_identity_service_gateway] = lambda: fake_gateway
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
    app.dependency_overrides.clear()


async def test_reenvia_el_correo_y_devuelve_la_auditoria(bff_client, fake_gateway):
    response = await bff_client.get(
        "/api/v1/bff-web/consentimientos", params={"correo": "ana@example.com"}
    )

    assert response.status_code == 200
    assert response.json() == AUDITORIA
    assert fake_gateway.params == {"correo": "ana@example.com"}


async def test_reenvia_la_identificacion(bff_client, fake_gateway):
    await bff_client.get(
        "/api/v1/bff-web/consentimientos", params={"identificacion": "1020304050"}
    )

    assert fake_gateway.params == {"identificacion": "1020304050"}


async def test_ignora_parametros_desconocidos(bff_client, fake_gateway):
    await bff_client.get(
        "/api/v1/bff-web/consentimientos",
        params={"correo": "ana@example.com", "otro": "x"},
    )

    assert fake_gateway.params == {"correo": "ana@example.com"}


@pytest.mark.parametrize("codigo", [404, 422, 503])
async def test_propaga_los_errores_de_identity(bff_client, fake_gateway, codigo):
    fake_gateway.error = (codigo, "detalle")

    response = await bff_client.get(
        "/api/v1/bff-web/consentimientos", params={"correo": "ana@example.com"}
    )

    assert response.status_code == codigo
    assert response.json()["detail"] == "detalle"


@pytest.mark.parametrize("metodo", ["POST", "PUT", "PATCH", "DELETE"])
async def test_es_de_solo_lectura(bff_client, metodo):
    response = await bff_client.request(metodo, "/api/v1/bff-web/consentimientos")

    assert response.status_code == 405
