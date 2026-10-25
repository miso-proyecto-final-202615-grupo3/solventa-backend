from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.core.config import settings
from src.infrastructure.gateways.identity_service_gateway import IdentityGatewayError
from src.main import app
from src.presentation.dependencies import get_identity_service_gateway


PATH = "/api/v1/bff-mobile/activacion/sesiones"


class GatewayFake:
    def __init__(self) -> None:
        self.payload: tuple[str, dict, str] | None = None
        self.error: IdentityGatewayError | None = None

    async def iniciar_activacion_movil(self, correo, dispositivo, correlation_id):
        if self.error:
            raise self.error
        self.payload = (correo, dispositivo, correlation_id)
        return {
            "dispositivo_vinculado": False,
            "sesion_id": "sesion-1",
            "expira_en": "2026-10-25T12:02:00Z",
            "captura": {"type": "FRAMES"},
            "intentos_restantes": 3,
        }


@pytest.fixture
async def client(monkeypatch):
    gateway = GatewayFake()
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "ALLOW_DEMO_ACTIVATION_WITHOUT_JWT", True)
    app.dependency_overrides[get_identity_service_gateway] = lambda: gateway
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http, gateway
    app.dependency_overrides.clear()


def _payload() -> dict:
    return {
        "correo": "ana@example.com",
        "installation_id": str(uuid4()),
        "plataforma": "ANDROID",
        "modelo": "Pixel",
        "version_so": "15",
    }


async def test_inicia_activacion_demo_sin_jwt(client):
    http, gateway = client

    response = await http.post(PATH, json=_payload(), headers={"X-Correlation-Id": "corr-1"})

    assert response.status_code == 201
    assert response.json()["sesion_id"] == "sesion-1"
    assert gateway.payload is not None
    assert gateway.payload[0] == "ana@example.com"
    assert gateway.payload[2] == "corr-1"


async def test_rechaza_demo_fuera_de_desarrollo(client, monkeypatch):
    http, _ = client
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")

    response = await http.post(PATH, json=_payload())

    assert response.status_code == 401


async def test_requiere_correo_en_el_modo_demo(client):
    http, _ = client
    payload = _payload()
    payload.pop("correo")

    response = await http.post(PATH, json=payload)

    assert response.status_code == 422
