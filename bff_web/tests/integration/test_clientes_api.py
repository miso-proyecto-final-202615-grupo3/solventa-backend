import pytest
from httpx import ASGITransport, AsyncClient

from src.infrastructure.gateways.identity_service_gateway import (
    IdentityGatewayError,
)
from src.main import app
from src.presentation.dependencies import get_identity_service_gateway

PAYLOAD = {
    "nombres": "Ana",
    "apellidos": "Pérez",
    "tipo_documento": "CC",
    "numero_identificacion": "1020304050",
    "correo": "ana.perez@example.com",
    "password": "Secreta123",
    "fecha_nacimiento": "1990-05-15",
    "pais_residencia": "Colombia",
    "telefono": "+573001234567",
}


class FakeIdentityGateway:
    def __init__(self):
        self.resultado: dict | None = None
        self.error: tuple[int, str] | None = None

    async def registrar_cliente(self, payload: dict) -> dict:
        self._comprobar()
        return self.resultado

    async def autenticar_cliente(self, payload: dict) -> dict:
        self._comprobar()
        return self.resultado

    def _comprobar(self) -> None:
        if self.error is not None:
            status, detail = self.error
            raise IdentityGatewayError(status, detail)


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


async def test_registro_devuelve_201(bff_client: AsyncClient, fake_gateway):
    fake_gateway.resultado = {**PAYLOAD, "id": "uuid", "estado_kyc": "PENDIENTE"}

    response = await bff_client.post("/api/v1/bff-web/clientes/registro", json=PAYLOAD)

    assert response.status_code == 201
    assert response.json()["correo"] == PAYLOAD["correo"]


async def test_registro_propaga_409(bff_client: AsyncClient, fake_gateway):
    fake_gateway.error = (409, "Ya existe un cliente con ese correo.")

    response = await bff_client.post("/api/v1/bff-web/clientes/registro", json=PAYLOAD)

    assert response.status_code == 409
    assert "Ya existe" in response.json()["detail"]


async def test_registro_devuelve_422_con_payload_invalido(
    bff_client: AsyncClient,
):
    invalid = {**PAYLOAD, "correo": "no-es-correo"}

    response = await bff_client.post("/api/v1/bff-web/clientes/registro", json=invalid)

    assert response.status_code == 422


async def test_autenticar_devuelve_tokens(bff_client: AsyncClient, fake_gateway):
    fake_gateway.resultado = {
        "access_token": "access-123",
        "id_token": "id-123",
        "refresh_token": "refresh-123",
        "expires_in": 3600,
        "token_type": "Bearer",
    }

    response = await bff_client.post(
        "/api/v1/bff-web/clientes/autenticar",
        json={"correo": "ana.perez@example.com", "password": "Secreta123"},
    )

    assert response.status_code == 200
    assert response.json()["access_token"] == "access-123"


async def test_autenticar_propaga_error_de_identidad(
    bff_client: AsyncClient, fake_gateway
):
    fake_gateway.error = (503, "El servicio de identidad no está disponible.")

    response = await bff_client.post(
        "/api/v1/bff-web/clientes/autenticar",
        json={"correo": "ana.perez@example.com", "password": "Secreta123"},
    )

    assert response.status_code == 503