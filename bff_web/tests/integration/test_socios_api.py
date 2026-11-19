import pytest

from src.presentation.dependencies import (
    get_identity_socios_gateway,
    require_socios_admin,
)
from src.main import app

BASE = "/api/v1/bff-web/socios"


class GatewaySocios:
    actor_id = None
    payload = None
    key_call = None

    async def registrar_socio(self, payload, actor_id, correlation_id=None):
        self.payload = payload
        self.actor_id = actor_id
        return {
            "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            **payload,
            "estado": "PENDIENTE",
            "creado_en": "2026-11-16T15:00:00Z",
        }

    async def api_keys(self, method, socio_id, key_id=None):
        self.key_call = (method, socio_id, key_id)
        if method == "POST":
            return {"api_key_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "fecha_generacion": "2026-11-18T00:00:00Z", "api_key": "secreta"}
        return None if method == "DELETE" else []


@pytest.fixture
async def socios_client(async_client):
    gateway = GatewaySocios()
    app.dependency_overrides[require_socios_admin] = lambda: "operator-sub"
    app.dependency_overrides[get_identity_socios_gateway] = lambda: gateway
    yield async_client, gateway
    app.dependency_overrides.clear()


async def test_registra_socio_y_propaga_actor_validado(socios_client):
    client, gateway = socios_client
    payload = {
        "nombre": "Banco Andino",
        "correo": "socio@yopmail.com",
        "tipo_socio": "Banco",
        "canal_integracion": "API",
    }

    response = await client.post(BASE, json=payload)

    assert response.status_code == 201
    assert response.json()["estado"] == "PENDIENTE"
    assert gateway.payload == payload
    assert gateway.actor_id == "operator-sub"


async def test_rechaza_solicitud_sin_autenticacion(async_client):
    response = await async_client.post(
        BASE,
        json={
        "nombre": "Banco Andino",
        "correo": "socio@yopmail.com",
            "tipo_socio": "Banco",
            "canal_integracion": "API",
        },
    )

    assert response.status_code == 401


async def test_rechaza_payload_invalido(socios_client):
    client, _ = socios_client

    response = await client.post(
        BASE,
        json={"nombre": " ", "correo": "socio@yopmail.com", "tipo_socio": "Banco", "canal_integracion": "API"},
    )

    assert response.status_code == 422


async def test_admin_gestiona_api_keys(socios_client):
    client, gateway = socios_client
    socio = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    key = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    created = await client.post(f"{BASE}/{socio}/api-keys")
    assert created.status_code == 201
    assert created.headers["cache-control"] == "no-store"
    assert created.json()["api_key"] == "secreta"
    assert gateway.key_call == ("POST", socio, None)
    assert (await client.delete(f"{BASE}/{socio}/api-keys/{key}")).status_code == 204
    assert gateway.key_call == ("DELETE", socio, key)


async def test_claves_requieren_admin(async_client):
    response = await async_client.post(f"{BASE}/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/api-keys")
    assert response.status_code == 401
