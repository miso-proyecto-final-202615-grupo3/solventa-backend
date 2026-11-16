import pytest

from src.presentation.dependencies import (
    get_partners_service_gateway,
    require_socios_admin,
)
from src.main import app

BASE = "/api/v1/bff-web/socios"


class GatewaySocios:
    actor_id = None
    payload = None

    async def registrar_socio(self, payload, actor_id, correlation_id=None):
        self.payload = payload
        self.actor_id = actor_id
        return {
            "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            **payload,
            "estado": "PENDIENTE",
            "creado_en": "2026-11-16T15:00:00Z",
        }


@pytest.fixture
async def socios_client(async_client):
    gateway = GatewaySocios()
    app.dependency_overrides[require_socios_admin] = lambda: "operator-sub"
    app.dependency_overrides[get_partners_service_gateway] = lambda: gateway
    yield async_client, gateway
    app.dependency_overrides.clear()


async def test_registra_socio_y_propaga_actor_validado(socios_client):
    client, gateway = socios_client
    payload = {
        "nombre": "Banco Andino",
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
            "tipo_socio": "Banco",
            "canal_integracion": "API",
        },
    )

    assert response.status_code == 401


async def test_rechaza_payload_invalido(socios_client):
    client, _ = socios_client

    response = await client.post(
        BASE,
        json={"nombre": " ", "tipo_socio": "Banco", "canal_integracion": "API"},
    )

    assert response.status_code == 422
