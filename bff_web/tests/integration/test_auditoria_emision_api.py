from uuid import UUID

import pytest

from src.core.config import settings
from src.infrastructure.gateways.payments_service_gateway import PaymentsGatewayError
from src.presentation.dependencies import (
    get_identity_service_gateway,
    get_insurancepolicies_service_gateway,
    get_payments_service_gateway,
    get_quotingengine_service_gateway,
    require_auditor,
)
from src.main import app

POLIZA_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
COTIZACION_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
CLIENTE_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
BASE = "/api/v1/bff-web/auditoria-emision"


def evento(evento_id: str, tipo: str, fecha: str, resultado: str) -> dict:
    return {
        "evento_id": str(UUID(int=int(evento_id))),
        "cotizacion_id": str(COTIZACION_ID),
        "cliente_id": str(CLIENTE_ID),
        "tipo": tipo,
        "ocurrido_en": fecha,
        "origen": "servicio-prueba",
        "actor_id": None,
        "resultado": resultado,
        "referencia_id": evento_id,
        "correlation_id": "corr-1",
        "detalles": {},
    }


class GatewayPolizas:
    async def consultar_trazabilidad_poliza(self, numero, token):
        assert token == "token-interno"
        return {
            "poliza_id": str(POLIZA_ID),
            "numero": numero,
            "cotizacion_id": str(COTIZACION_ID),
            "cliente_id": str(CLIENTE_ID),
            "eventos": [evento("6", "POLIZA_EMITIDA", "2026-11-13T16:00:00Z", "EMITIDA")],
        }


class GatewayCotizaciones:
    async def consultar_trazabilidad_condiciones(self, cotizacion_id, token):
        assert cotizacion_id == str(COTIZACION_ID) and token == "token-interno"
        return [evento("1", "CONDICIONES_ACEPTADAS", "2026-11-13T12:00:00Z", "ACEPTADA")]


class GatewayIdentidad:
    async def consultar_trazabilidad_kyc_aml(self, cotizacion_id, token):
        assert cotizacion_id == str(COTIZACION_ID) and token == "token-interno"
        return [evento("2", "KYC_AML_RESULTADO", "2026-11-13T13:00:00Z", "APROBADA")]


class GatewayPagos:
    fallar = False

    async def consultar_trazabilidad_pagos(self, cotizacion_id, token):
        if self.fallar:
            raise PaymentsGatewayError(503, "falló")
        assert cotizacion_id == COTIZACION_ID and token == "token-interno"
        return [evento("4", "PAGO_RESULTADO", "2026-11-13T15:00:00Z", "APROBADO")]


@pytest.fixture
async def audit_client(async_client, monkeypatch):
    monkeypatch.setattr(settings, "TRAZABILIDAD_INTERNAL_TOKEN", "token-interno")
    pagos = GatewayPagos()
    app.dependency_overrides[require_auditor] = lambda: "auditor-sub"
    app.dependency_overrides[get_insurancepolicies_service_gateway] = GatewayPolizas
    app.dependency_overrides[get_quotingengine_service_gateway] = GatewayCotizaciones
    app.dependency_overrides[get_identity_service_gateway] = GatewayIdentidad
    app.dependency_overrides[get_payments_service_gateway] = lambda: pagos
    yield async_client, pagos
    app.dependency_overrides.clear()


async def test_une_y_ordena_todos_los_eventos_de_emision(audit_client):
    client, _ = audit_client

    response = await client.get(BASE, params={"numero_poliza": "POL-20261113-AB12CD34"})

    assert response.status_code == 200, response.text
    cuerpo = response.json()
    assert cuerpo["poliza_id"] == str(POLIZA_ID)
    assert [evento["tipo"] for evento in cuerpo["eventos"]] == [
        "CONDICIONES_ACEPTADAS",
        "KYC_AML_RESULTADO",
        "PAGO_RESULTADO",
        "POLIZA_EMITIDA",
    ]


async def test_no_devuelve_historial_parcial_si_falla_una_fuente(audit_client):
    client, pagos = audit_client
    pagos.fallar = True

    response = await client.get(BASE, params={"numero_poliza": "POL-20261113-AB12CD34"})

    assert response.status_code == 503
    assert "eventos" not in response.json()


async def test_rechaza_usuario_sin_token():
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(BASE, params={"numero_poliza": "POL-20261113-AB12CD34"})
    assert response.status_code == 401
