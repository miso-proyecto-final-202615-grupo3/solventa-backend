"""HU4.2.1: listado de siniestros del cliente y URL de descarga de evidencias en el BFF Móvil."""
import json
import logging
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from src.infrastructure.gateways.insuranceclaims_service_gateway import (
    ClaimsGatewayError,
    InsuranceClaimsServiceGateway,
)
from src.main import app
from src.presentation.dependencies import get_cliente_id, get_insuranceclaims_service_gateway

BASE = "/api/v1/bff-mobile/siniestros"
CLIENTE_ID = "11111111-1111-4111-8111-111111111111"
POLIZA_ID = "8d2b6c1e-4a7f-4f0e-9a51-0c6b1d9e2f10"
SINIESTRO_ID = "c41f0e2a-9b7d-4e55-8a0c-2f6d1b3e9a77"
EVIDENCIA_ID = "5e0c2d8a-1f43-4b7e-9c0d-6a2b8e4f1c33"
CONTRACTS = Path(__file__).resolve().parents[3] / "docs" / "contracts"


def _muestra(ruta: str) -> dict:
    return json.loads((CONTRACTS / ruta).read_text(encoding="utf-8"))


class ClaimsFake:
    def __init__(self) -> None:
        self.llamadas: list[tuple] = []
        self.error: ClaimsGatewayError | None = None

    async def listar_siniestros(self, cliente_id, correlation_id, poliza_id, pagina, tamano):
        self.llamadas.append(("listar", cliente_id, poliza_id, pagina, tamano))
        if self.error:
            raise self.error
        return _muestra("siniestros/listado-response.json")

    async def obtener_descarga_evidencia(self, cliente_id, siniestro_id, evidencia_id, correlation_id):
        self.llamadas.append(("descarga", cliente_id, siniestro_id, evidencia_id))
        if self.error:
            raise self.error
        return _muestra("evidencias/descarga-response.json")


@pytest.fixture
async def client():
    claims = ClaimsFake()
    app.dependency_overrides[get_insuranceclaims_service_gateway] = lambda: claims
    app.dependency_overrides[get_cliente_id] = lambda: CLIENTE_ID
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http, claims
    app.dependency_overrides.clear()


async def test_listado_reenvia_cliente_filtro_y_paginacion(client):
    http, claims = client

    sin_filtro = await http.get(BASE)
    con_filtro = await http.get(BASE, params={"poliza_id": POLIZA_ID, "pagina": 2, "tamano": 5})

    assert sin_filtro.status_code == 200
    assert sin_filtro.json() == _muestra("siniestros/listado-response.json")
    assert con_filtro.status_code == 200
    assert claims.llamadas == [
        ("listar", CLIENTE_ID, None, 1, 20),
        ("listar", CLIENTE_ID, POLIZA_ID, 2, 5),
    ]


@pytest.mark.parametrize("params", [{"pagina": 0}, {"tamano": 51}, {"poliza_id": "abc"}])
async def test_listado_con_parametros_invalidos(client, params):
    http, claims = client

    response = await http.get(BASE, params=params)

    # Validación de FastAPI, igual que en el resto de rutas del BFF: no llega a MS Siniestros.
    assert response.status_code == 422
    assert claims.llamadas == []


async def test_listado_con_siniestros_caido(client):
    http, claims = client
    claims.error = ClaimsGatewayError(503, "El servicio de siniestros no está disponible.")

    response = await http.get(BASE)

    assert response.status_code == 503
    assert response.json()["codigo"] == "SERVICIO_NO_DISPONIBLE"


async def test_descarga_reenvia_y_no_registra_la_url(client, caplog):
    http, claims = client
    caplog.set_level(logging.DEBUG)

    response = await http.get(f"{BASE}/{SINIESTRO_ID}/evidencias/{EVIDENCIA_ID}/descarga")

    assert response.status_code == 200
    cuerpo = response.json()
    assert cuerpo["url"] == _muestra("evidencias/descarga-response.json")["url"]
    assert cuerpo["expira_en"] == "2026-11-10T20:10:00Z"
    assert claims.llamadas == [("descarga", CLIENTE_ID, SINIESTRO_ID, EVIDENCIA_ID)]
    assert "X-Amz-Signature" not in caplog.text


@pytest.mark.parametrize(
    ("status", "codigo"),
    [(404, "EVIDENCIA_NO_ENCONTRADA"), (404, "SINIESTRO_NO_ENCONTRADO"), (409, "EVIDENCIA_NO_DISPONIBLE")],
)
async def test_descarga_traduce_los_errores_del_servicio(client, status, codigo):
    http, claims = client
    claims.error = ClaimsGatewayError(status, {"codigo": codigo, "mensaje": "x"})

    response = await http.get(f"{BASE}/{SINIESTRO_ID}/evidencias/{EVIDENCIA_ID}/descarga")

    assert (response.status_code, response.json()["codigo"]) == (status, codigo)


async def test_gateway_envia_parametros_y_rutas():
    recibido = []

    def handler(request: httpx.Request) -> httpx.Response:
        recibido.append((request.url.path, dict(request.url.params), request.headers["x-cliente-id"]))
        return httpx.Response(200, json={"ok": True})

    gateway = InsuranceClaimsServiceGateway("http://claims", transport=httpx.MockTransport(handler))

    await gateway.listar_siniestros("cli", "corr", None, 1, 20)
    await gateway.listar_siniestros("cli", "corr", POLIZA_ID, 3, 10)
    await gateway.obtener_descarga_evidencia("cli", SINIESTRO_ID, EVIDENCIA_ID, "corr")

    assert recibido[0] == ("/api/v1/insuranceclaims-service/siniestros", {"pagina": "1", "tamano": "20"}, "cli")
    assert recibido[1][1] == {"pagina": "3", "tamano": "10", "poliza_id": POLIZA_ID}
    assert recibido[2][0] == (
        f"/api/v1/insuranceclaims-service/siniestros/{SINIESTRO_ID}/evidencias/{EVIDENCIA_ID}/descarga"
    )
