import base64
import json

import pytest
from httpx import ASGITransport, AsyncClient

from src.infrastructure.gateways.identity_service_gateway import (
    IdentityGatewayError,
)
from src.main import app
from src.presentation.dependencies import get_identity_service_gateway

LOGIN_PATH = "/api/v1/bff-mobile/auth/login"
CREDENCIALES = {"correo": "ana.perez@example.com", "password": "Secreta123"}


def _id_token(claims: dict) -> str:
    def b64(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")

    return f"{b64({'alg': 'RS256'})}.{b64(claims)}.firma"


class FakeIdentityGateway:
    def __init__(self):
        self.resultado: dict | None = None
        self.error: tuple[int, str] | None = None
        self.llamadas: list[tuple[str, str]] = []

    async def autenticar_cliente(self, correo: str, password: str) -> dict:
        self.llamadas.append((correo, password))
        if self.error is not None:
            status, detail = self.error
            raise IdentityGatewayError(status, detail)
        return self.resultado


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


async def test_login_devuelve_sesion_con_correo_del_id_token(
    bff_client: AsyncClient, fake_gateway
):
    fake_gateway.resultado = {
        "access_token": "access-123",
        "id_token": _id_token({"email": "ana.perez@example.com"}),
        "refresh_token": "refresh-123",
        "expires_in": 3600,
        "token_type": "Bearer",
    }

    response = await bff_client.post(LOGIN_PATH, json=CREDENCIALES)

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "access_token": "access-123",
        "refresh_token": "refresh-123",
        "expires_in": 3600,
        "token_type": "Bearer",
        "correo": "ana.perez@example.com",
    }
    assert "id_token" not in body
    assert fake_gateway.llamadas == [("ana.perez@example.com", "Secreta123")]


async def test_login_sin_id_token_devuelve_correo_nulo(
    bff_client: AsyncClient, fake_gateway
):
    fake_gateway.resultado = {"access_token": "access-123"}

    response = await bff_client.post(LOGIN_PATH, json=CREDENCIALES)

    assert response.status_code == 200
    assert response.json()["correo"] is None


async def test_login_credenciales_invalidas_devuelve_401(
    bff_client: AsyncClient, fake_gateway
):
    fake_gateway.error = (401, "Credenciales inválidas.")

    response = await bff_client.post(LOGIN_PATH, json=CREDENCIALES)

    assert response.status_code == 401
    assert response.json()["detail"] == "Credenciales inválidas."


@pytest.mark.parametrize("status_identidad", [500, 503])
async def test_login_falla_de_identidad_devuelve_503(
    bff_client: AsyncClient, fake_gateway, status_identidad: int
):
    fake_gateway.error = (status_identidad, "boom interno")

    response = await bff_client.post(LOGIN_PATH, json=CREDENCIALES)

    assert response.status_code == 503
    assert "boom" not in response.json()["detail"]


async def test_login_con_correo_invalido_devuelve_422(bff_client: AsyncClient, fake_gateway):
    response = await bff_client.post(
        LOGIN_PATH, json={"correo": "no-es-correo", "password": "x"}
    )

    assert response.status_code == 422
    assert fake_gateway.llamadas == []


async def test_login_rechaza_campos_extra(bff_client: AsyncClient):
    response = await bff_client.post(LOGIN_PATH, json={**CREDENCIALES, "extra": 1})

    assert response.status_code == 422
