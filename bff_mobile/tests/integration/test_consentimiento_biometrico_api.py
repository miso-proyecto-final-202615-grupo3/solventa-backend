from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.infrastructure.gateways.identity_service_gateway import IdentityGatewayError
from src.main import app
from src.presentation.dependencies import get_cliente_autenticado, get_identity_service_gateway
from src.presentation.jwt_validator import ClienteAutenticado

PATH = "/api/v1/bff-mobile/consentimientos/biometrico"


class GatewayFake:
    def __init__(self) -> None:
        self.consulta: tuple[str, str] | None = None
        self.registro: tuple[str, dict, str] | None = None
        self.error: IdentityGatewayError | None = None

    async def consultar_consentimiento_biometrico(self, correo, correlation_id):
        if self.error:
            raise self.error
        self.consulta = (correo, correlation_id)
        return {"otorgado": True, "version_vigente": "1.0", "version_aceptada": "1.0",
                "decidido_en": "2026-11-02T15:00:00Z"}

    async def registrar_consentimiento_biometrico(self, correo, decision, correlation_id):
        if self.error:
            raise self.error
        self.registro = (correo, decision, correlation_id)
        return {"decision": decision["decision"], "version_terminos": decision["version_terminos"],
                "registrado_en": "2026-11-02T15:00:01Z"}


@pytest.fixture
async def client():
    gateway = GatewayFake()
    app.dependency_overrides[get_identity_service_gateway] = lambda: gateway
    app.dependency_overrides[get_cliente_autenticado] = lambda: ClienteAutenticado("ana@example.com", "sub-1")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http, gateway
    app.dependency_overrides.clear()


def _payload(**cambios) -> dict:
    payload = {
        "decision": "ACEPTADO",
        "version_terminos": "1.0",
        "installation_id": str(uuid4()),
        "decidido_en": datetime.now(UTC).isoformat(),
    }
    payload.update(cambios)
    return payload


async def test_consulta_usa_el_correo_del_token(client):
    http, gateway = client

    response = await http.get(PATH, headers={"X-Correlation-Id": "corr-1"})

    assert response.status_code == 200
    assert response.json() == {"otorgado": True, "version_vigente": "1.0", "version_aceptada": "1.0",
                               "decidido_en": "2026-11-02T15:00:00Z"}
    assert gateway.consulta == ("ana@example.com", "corr-1")


@pytest.mark.parametrize("decision", ["ACEPTADO", "RECHAZADO"])
async def test_registra_la_decision_con_el_correo_del_token(client, decision):
    http, gateway = client
    payload = _payload(decision=decision)

    response = await http.post(PATH, json=payload, headers={"X-Correlation-Id": "corr-2"})

    assert response.status_code == 201
    assert response.json() == {"decision": decision, "version_terminos": "1.0",
                               "registrado_en": "2026-11-02T15:00:01Z"}
    correo, enviado, correlation_id = gateway.registro
    assert correo == "ana@example.com"
    assert enviado["decision"] == decision
    assert enviado["installation_id"] == payload["installation_id"]
    assert correlation_id == "corr-2"


@pytest.mark.parametrize(
    "cambios",
    [
        {"decision": "QUIZAS"},
        {"decidido_en": "2026-11-02T15:00:00"},
        {"installation_id": "x"},
        {"correo": "otro@example.com"},
    ],
    ids=["decision", "fecha-sin-zona", "instalacion", "correo-en-el-body"],
)
async def test_datos_invalidos_responden_422(client, cambios):
    http, gateway = client

    response = await http.post(PATH, json=_payload(**cambios))

    assert response.status_code == 422
    assert gateway.registro is None


async def test_version_desactualizada_conserva_el_codigo_de_identidad(client):
    http, gateway = client
    gateway.error = IdentityGatewayError(409, {"codigo": "VERSION_TERMINOS_DESACTUALIZADA", "mensaje": "m"})

    response = await http.post(PATH, json=_payload(version_terminos="0.9"), headers={"X-Correlation-Id": "c"})

    assert response.status_code == 409
    assert response.json() == {"codigo": "VERSION_TERMINOS_DESACTUALIZADA", "mensaje": "m", "correlation_id": "c"}


async def test_error_5xx_de_identidad_se_traduce_a_503(client):
    http, gateway = client
    gateway.error = IdentityGatewayError(500, "detalle interno")

    response = await http.get(PATH)

    assert response.status_code == 503
    assert response.json()["codigo"] == "SERVICIO_NO_DISPONIBLE"
    assert "detalle interno" not in response.text


async def test_sin_token_responde_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        get = await http.get(PATH)
        post = await http.post(PATH, json=_payload())

    assert get.status_code == 401
    assert post.status_code == 401
    assert get.json()["codigo"] == "NO_AUTENTICADO"
