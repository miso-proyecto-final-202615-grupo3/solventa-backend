import json
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.core.config import settings
from src.infrastructure.gateways.identity_service_gateway import IdentityGatewayError
from src.main import app
from src.presentation import dependencies
from src.presentation.dependencies import get_identity_service_gateway
from src.presentation.jwt_validator import IdentityLookupUnavailableError


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
            "captura": {"tipo": "FRAMES", "reto": {"gesto": "BLINK", "nonce": "n"}},
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
        "installation_id": str(uuid4()),
        "plataforma": "ANDROID",
        "modelo": "Pixel",
        "version_so": "15",
    }


async def test_inicia_activacion_demo_sin_jwt(client):
    http, gateway = client

    response = await http.post(PATH, json=_payload(), headers={"X-Correlation-Id": "corr-1", "X-Demo-Correo": "ana@example.com"})

    assert response.status_code == 201
    assert response.json()["sesion_id"] == "sesion-1"
    assert gateway.payload is not None
    assert gateway.payload[0] == "ana@example.com"
    assert gateway.payload[2] == "corr-1"


async def test_rechaza_demo_fuera_de_desarrollo(client, monkeypatch):
    http, _ = client
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")

    response = await http.post(PATH, json=_payload(), headers={"X-Demo-Correo": "ana@example.com"})

    assert response.status_code == 401


async def test_sin_token_ni_identidad_demo_responde_401_con_formato_comun(client):
    http, _ = client

    response = await http.post(PATH, json=_payload(), headers={"X-Correlation-Id": "corr-9"})

    assert response.status_code == 401
    assert response.json() == {
        "codigo": "NO_AUTENTICADO",
        "mensaje": "Se requiere un token Bearer válido.",
        "correlation_id": "corr-9",
    }


async def test_cognito_caido_responde_503_y_no_401(client, monkeypatch):
    http, _ = client

    class ValidadorSinCognito:
        def validar(self, token):
            raise IdentityLookupUnavailableError("sin red")

    monkeypatch.setattr(dependencies, "get_cognito_jwt_validator", lambda: ValidadorSinCognito())

    response = await http.post(PATH, json=_payload(), headers={"Authorization": "Bearer x", "X-Correlation-Id": "corr-10"})

    assert response.status_code == 503
    assert response.json()["codigo"] == "SERVICIO_NO_DISPONIBLE"


class VerificacionGatewayFake(GatewayFake):
    def __init__(self):
        super().__init__()
        self.verificacion = None

    async def verificar_activacion_movil(self, sesion_id, correo, metadata, frames, correlation_id):
        if self.error:
            raise self.error
        self.verificacion = (sesion_id, correo, json.loads(metadata), dict(frames))
        return {
            "resultado": "APROBADO", "folio": "propio-1", "intento": 1, "intentos_restantes": 3,
            "dispositivo_vinculado": True, "vinculado_en": "2026-10-31T12:00:00Z", "motivo": None,
        }


@pytest.fixture
async def verif_client(monkeypatch):
    gateway = VerificacionGatewayFake()
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "ALLOW_DEMO_ACTIVATION_WITHOUT_JWT", True)
    app.dependency_overrides[get_identity_service_gateway] = lambda: gateway
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http, gateway
    app.dependency_overrides.clear()


VERIF = "/api/v1/bff-mobile/activacion/sesiones/sesion-1/verificacion"
DEMO = {"X-Demo-Correo": "ana@example.com"}
JPEG = bytes([0xFF, 0xD8, 0xFF]) + b"x" * 10


def _frames():
    return {name: (f"{name}.jpg", JPEG, "image/jpeg") for name in ("frame_inicio", "frame_gesto", "frame_fin")}


async def test_verificacion_frames_toma_el_correo_de_la_identidad(verif_client):
    http, gateway = verif_client
    metadata = {"nonce": "n", "capturas": {"inicio": "a", "gesto": "b", "fin": "c"}}

    response = await http.post(VERIF, data={"metadata": json.dumps(metadata)}, files=_frames(), headers=DEMO)

    assert response.status_code == 200
    assert gateway.verificacion[1] == "ana@example.com"


async def test_verificacion_sdk_no_exige_frames(verif_client):
    http, gateway = verif_client

    response = await http.post(VERIF, data={"metadata": json.dumps({"resultado_sdk": "COMPLETED"})}, headers=DEMO)

    assert response.status_code == 200
    assert gateway.verificacion[3] == {}


async def test_frame_grande_responde_413(verif_client):
    http, _ = verif_client
    files = _frames()
    files["frame_fin"] = ("frame_fin.jpg", JPEG + b"x" * 524_288, "image/jpeg")
    metadata = {"nonce": "n", "capturas": {"inicio": "a", "gesto": "b", "fin": "c"}}

    response = await http.post(VERIF, data={"metadata": json.dumps(metadata)}, files=files, headers=DEMO)

    assert response.status_code == 413
    assert response.json()["codigo"] == "CAPTURA_DEMASIADO_GRANDE"


async def test_error_5xx_de_identidad_no_filtra_detalles(verif_client):
    http, gateway = verif_client
    gateway.error = IdentityGatewayError(500, {"codigo": "TRACE", "mensaje": "stack interno"})

    response = await http.post(VERIF, data={"metadata": json.dumps({"resultado_sdk": "COMPLETED"})}, headers=DEMO)

    assert response.status_code == 503
    assert response.json()["codigo"] == "SERVICIO_NO_DISPONIBLE"


async def test_codigo_de_negocio_de_identidad_se_conserva(verif_client):
    http, gateway = verif_client
    gateway.error = IdentityGatewayError(429, {"codigo": "INTENTOS_AGOTADOS", "mensaje": "Agotados"})

    response = await http.post(VERIF, data={"metadata": json.dumps({"resultado_sdk": "COMPLETED"})}, headers=DEMO)

    assert response.status_code == 429
    assert response.json()["codigo"] == "INTENTOS_AGOTADOS"
