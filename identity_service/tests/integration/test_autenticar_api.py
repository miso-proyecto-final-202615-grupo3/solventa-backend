import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.presentation.dependencies import get_identity_provider

CREDENCIALES = {
    "correo": "ana.perez@example.com",
    "password": "Secreta123",
}


@pytest.fixture
async def autenticar_client(fake_identity_provider):
    app.dependency_overrides[get_identity_provider] = lambda: fake_identity_provider

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, fake_identity_provider

    app.dependency_overrides.clear()


async def test_autenticacion_exitosa(autenticar_client):
    client, _ = autenticar_client

    response = await client.post(
        "/api/v1/identity-service/clientes/autenticar", json=CREDENCIALES
    )

    assert response.status_code == 200
    data = response.json()
    assert data["access_token"] == "access-123"
    assert data["id_token"] == "id-123"
    assert data["token_type"] == "Bearer"


async def test_autenticacion_rechaza_credenciales_invalidas(autenticar_client):
    client, fake = autenticar_client
    fake.credenciales_invalidas = True

    response = await client.post(
        "/api/v1/identity-service/clientes/autenticar", json=CREDENCIALES
    )

    assert response.status_code == 401


async def test_autenticacion_devuelve_503_si_identidad_falla(autenticar_client):
    client, fake = autenticar_client
    fake.fallar_autenticacion = True

    response = await client.post(
        "/api/v1/identity-service/clientes/autenticar", json=CREDENCIALES
    )

    assert response.status_code == 503


async def test_autenticacion_rechaza_payload_invalido(autenticar_client):
    client, _ = autenticar_client
    invalid = {**CREDENCIALES, "correo": "no-es-correo"}

    response = await client.post(
        "/api/v1/identity-service/clientes/autenticar", json=invalid
    )

    assert response.status_code == 422