import json
import pytest
import uuid
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
        self.registro_payload: bytes | None = None
        self.registro_content_type: str | None = None
        self.autenticacion_payload: bytes | None = None
        self.consentimiento_payload: bytes | None = None
        self.cliente_id: str | None = None

    async def registrar_cliente(self, payload: bytes, content_type: str) -> dict:
        self._comprobar()
        self.registro_payload = payload
        self.registro_content_type = content_type
        return self.resultado

    async def autenticar_cliente(self, payload: bytes, content_type: str) -> dict:
        self._comprobar()
        self.autenticacion_payload = payload
        return self.resultado

    async def actualizar_consentimiento(
        self, cliente_id: str, payload: bytes, content_type: str
    ) -> dict:
        self._comprobar()
        self.cliente_id = cliente_id
        self.consentimiento_payload = payload
        return self.resultado

    async def obtener_perfil_cliente(self, cliente_id: str) -> dict:
        self._comprobar()
        self.cliente_id = cliente_id
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


async def test_registro_reenvia_consentimiento_datos(bff_client, fake_gateway):
    fake_gateway.resultado = {"id": "uuid"}

    response = await bff_client.post(
        "/api/v1/bff-web/clientes/registro",
        json={**PAYLOAD, "consentimiento_datos": True},
    )

    assert response.status_code == 201
    assert json.loads(fake_gateway.registro_payload)["consentimiento_datos"] is True


async def test_registro_reenvia_payload_sin_validarlo(
    bff_client: AsyncClient, fake_gateway
):
    fake_gateway.resultado = {"id": "uuid"}
    payload = b'{"correo":"invalido","campo_extra":true}'

    response = await bff_client.post(
        "/api/v1/bff-web/clientes/registro",
        content=payload,
        headers={"content-type": "application/vnd.api+json"},
    )

    assert response.status_code == 201
    assert fake_gateway.registro_payload == payload
    assert fake_gateway.registro_content_type == "application/vnd.api+json"


async def test_registro_propaga_409(bff_client: AsyncClient, fake_gateway):
    fake_gateway.error = (409, "Ya existe un cliente con ese correo.")

    response = await bff_client.post("/api/v1/bff-web/clientes/registro", json=PAYLOAD)

    assert response.status_code == 409
    assert "Ya existe" in response.json()["detail"]


async def test_autenticar_devuelve_tokens(bff_client: AsyncClient, fake_gateway):
    fake_gateway.resultado = {
        "access_token": "access-123",
        "id_token": "id-123",
        "refresh_token": "refresh-123",
        "expires_in": 3600,
        "token_type": "Bearer",
    }

    payload = b'{"correo":"invalido","campo_extra":true}'
    response = await bff_client.post(
        "/api/v1/bff-web/clientes/autenticar",
        content=payload,
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 200
    assert response.json()["access_token"] == "access-123"
    assert fake_gateway.autenticacion_payload == payload


async def test_autenticar_propaga_error_de_identidad(
    bff_client: AsyncClient, fake_gateway
):
    fake_gateway.error = (503, "El servicio de identidad no está disponible.")

    response = await bff_client.post(
        "/api/v1/bff-web/clientes/autenticar",
        json={"correo": "ana.perez@example.com", "password": "Secreta123"},
    )

    assert response.status_code == 503


async def test_actualizar_consentimiento_reenvia_estado(
    bff_client: AsyncClient, fake_gateway
):
    cliente_id = uuid.uuid4()
    fake_gateway.resultado = {"estado": "INVALIDO"}
    payload = b'{"estado":"INVALIDO"}'

    response = await bff_client.put(
        f"/api/v1/bff-web/clientes/{cliente_id}/consentimiento",
        content=payload,
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 200
    assert response.json()["estado"] == "INVALIDO"
    assert fake_gateway.cliente_id == str(cliente_id)
    assert fake_gateway.consentimiento_payload == payload


async def test_obtener_perfil_propaga_403(bff_client: AsyncClient, fake_gateway):
    cliente_id = uuid.uuid4()
    fake_gateway.error = (403, "El consentimiento no está activo.")

    response = await bff_client.get(
        f"/api/v1/bff-web/clientes/{cliente_id}/perfil"
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "El consentimiento no está activo."

