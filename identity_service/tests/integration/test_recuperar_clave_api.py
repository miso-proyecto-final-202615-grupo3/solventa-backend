import pytest

from src.application.ports.identity_provider import (
    IdentityProviderError,
    PasswordRecoveryCodeError,
)
from src.main import app
from src.presentation.dependencies import get_identity_provider

BASE = "/api/v1/identity-service/clientes"


class FakePasswordRecoveryProvider:
    fail_request = False
    fail_confirmation = False
    requests: list[str]
    confirmations: list[tuple[str, str, str]]

    def __init__(self):
        self.requests = []
        self.confirmations = []

    async def solicitar_recuperacion_clave(self, correo: str) -> None:
        self.requests.append(correo)
        if self.fail_request:
            raise IdentityProviderError("Cognito no disponible.")

    async def confirmar_recuperacion_clave(
        self, correo: str, codigo: str, nueva_clave: str
    ) -> None:
        self.confirmations.append((correo, codigo, nueva_clave))
        if self.fail_confirmation:
            raise PasswordRecoveryCodeError("Código inválido o vencido.")


@pytest.fixture
async def recovery_client(async_client):
    provider = FakePasswordRecoveryProvider()
    app.dependency_overrides[get_identity_provider] = lambda: provider
    yield async_client, provider
    app.dependency_overrides.clear()


async def test_solicitar_recuperacion_responde_sin_revelar_existencia(recovery_client):
    client, provider = recovery_client

    response = await client.post(
        f"{BASE}/recuperar-clave", json={"correo": "ana@example.com"}
    )

    assert response.status_code == 202
    assert response.json()["mensaje"] == (
        "Si existe una cuenta con ese correo verificado, enviaremos un código."
    )
    assert provider.requests == ["ana@example.com"]


async def test_confirmar_codigo_actualiza_clave(recovery_client):
    client, provider = recovery_client

    response = await client.post(
        f"{BASE}/recuperar-clave/confirmar",
        json={
            "correo": "ana@example.com",
            "codigo": "123456",
            "nueva_clave": "NuevaClave123",
        },
    )

    assert response.status_code == 200
    assert provider.confirmations == [
        ("ana@example.com", "123456", "NuevaClave123")
    ]


async def test_codigo_invalido_se_devuelve_como_400(recovery_client):
    client, provider = recovery_client
    provider.fail_confirmation = True

    response = await client.post(
        f"{BASE}/recuperar-clave/confirmar",
        json={
            "correo": "ana@example.com",
            "codigo": "000000",
            "nueva_clave": "NuevaClave123",
        },
    )

    assert response.status_code == 400


async def test_error_de_cognito_no_revela_si_la_cuenta_existe(recovery_client):
    client, provider = recovery_client
    provider.fail_request = True

    response = await client.post(
        f"{BASE}/recuperar-clave", json={"correo": "ana@example.com"}
    )

    assert response.status_code == 503
