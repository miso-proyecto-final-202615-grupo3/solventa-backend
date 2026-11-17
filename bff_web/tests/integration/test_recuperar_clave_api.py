import json

import pytest

from src.infrastructure.gateways.identity_service_gateway import IdentityGatewayError
from src.presentation.dependencies import get_identity_service_gateway
from src.main import app

BASE = "/api/v1/bff-web/clientes/recuperar-clave"


class GatewayIdentidad:
    def __init__(self):
        self.solicitudes: list[dict] = []
        self.confirmaciones: list[dict] = []
        self.error: IdentityGatewayError | None = None

    async def solicitar_recuperacion_clave(self, payload, content_type):
        if self.error:
            raise self.error
        self.solicitudes.append(json.loads(payload))
        return {"mensaje": "Si existe una cuenta, enviaremos un código."}

    async def confirmar_recuperacion_clave(self, payload, content_type):
        if self.error:
            raise self.error
        self.confirmaciones.append(json.loads(payload))
        return {"mensaje": "Contraseña actualizada."}


@pytest.fixture
async def recovery_client(async_client):
    gateway = GatewayIdentidad()
    app.dependency_overrides[get_identity_service_gateway] = lambda: gateway
    yield async_client, gateway
    app.dependency_overrides.clear()


async def test_bff_reenvia_solicitud_de_codigo(recovery_client):
    client, gateway = recovery_client

    response = await client.post(BASE, json={"correo": "ana@example.com"})

    assert response.status_code == 202
    assert gateway.solicitudes == [{"correo": "ana@example.com"}]


async def test_bff_reenvia_confirmacion_de_codigo(recovery_client):
    client, gateway = recovery_client

    response = await client.post(
        f"{BASE}/confirmar",
        json={
            "correo": "ana@example.com",
            "codigo": "123456",
            "nueva_clave": "NuevaClave123",
        },
    )

    assert response.status_code == 200
    assert gateway.confirmaciones == [
        {
            "correo": "ana@example.com",
            "codigo": "123456",
            "nueva_clave": "NuevaClave123",
        }
    ]


async def test_bff_propaga_error_de_cognito(recovery_client):
    client, gateway = recovery_client
    gateway.error = IdentityGatewayError(503, "Cognito no disponible.")

    response = await client.post(BASE, json={"correo": "ana@example.com"})

    assert response.status_code == 503
