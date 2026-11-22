import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from src.infrastructure.gateways.insurancepolicies_service_gateway import PoliciesGatewayError
from src.infrastructure.gateways.quotingengine_service_gateway import QuotingEngineGatewayError
from src.main import app
from src.presentation.dependencies import (
    get_cliente_id,
    get_insurancepolicies_service_gateway,
    get_quotingengine_service_gateway,
)

BASE = "/api/v1/bff-mobile/polizas"
CLIENTE_ID = "11111111-1111-4111-8111-111111111111"
POLIZA_ID = "8d2b6c1e-4a7f-4f0e-9a51-0c6b1d9e2f10"
PRODUCTO_ID = "2c9a7e1b-6d5f-4a3c-8b10-1f2e3d4c5b6a"
COBERTURA_ID = "5f0c1a6e-2b3d-4c8e-9a10-7d6e5f4a3b21"
COBERTURA_SIN_NOMBRE = "6a1d2b7f-3c4e-4d9f-8b21-8e7f6a5b4c32"
CONTRATO = Path(__file__).resolve().parents[3] / "docs" / "contracts" / "polizas" / "billetera.json"

POLIZA = {
    "poliza_id": POLIZA_ID,
    "cliente_id": CLIENTE_ID,
    "cotizacion_id": "9e8d7c6b-5a49-4382-9170-6f5e4d3c2b1a",
    "producto_id": PRODUCTO_ID,
    "numero": "SLV-2026-08341",
    "estado": "EMITIDA",
    "vigencia_desde": "2026-03-12T00:00:00Z",
    "vigencia_hasta": "2027-03-12T00:00:00Z",
    "emitida_en": "2026-03-12T15:20:00Z",
    "ramo": "VIDA",
    "prima_total": "120000.00",
    "coberturas": [
        {"poliza_cobertura_id": "a1", "cobertura_id": COBERTURA_ID, "limite_asegurado": "200000000.00",
         "deducible": "0.00", "prima": "100000.00"},
        {"poliza_cobertura_id": "a2", "cobertura_id": COBERTURA_SIN_NOMBRE, "limite_asegurado": "50000000.00",
         "deducible": "0.00", "prima": "20000.00"},
    ],
    "historial": [{"evento": "no debe salir al móvil"}],
}
CATALOGO = [{
    "producto_id": PRODUCTO_ID, "codigo": "SEGURO_VIDA_HIPOTECARIO", "nombre": "Seguro de vida hipotecario",
    "ramo": "VIDA",
    "coberturas": [{"cobertura_id": COBERTURA_ID, "codigo": "MUERTE", "nombre": "Muerte por cualquier causa",
                    "limite_asegurado": "200000000.00", "deducible": "0.00"}],
}]
PDF = b"%PDF-1.4 certificado"


class PoliciesFake:
    def __init__(self) -> None:
        self.llamadas: list[tuple] = []
        self.error: PoliciesGatewayError | None = None
        self.polizas = [POLIZA]
        self.disposicion: str | None = 'attachment; filename="certificado-SLV-2026-08341.pdf"'

    async def listar_mis_polizas(self, cliente_id, correlation_id):
        self.llamadas.append(("listar", cliente_id, correlation_id))
        if self.error:
            raise self.error
        return self.polizas

    async def descargar_certificado(self, poliza_id, cliente_id, correlation_id):
        self.llamadas.append(("certificado", poliza_id, cliente_id, correlation_id))
        if self.error:
            raise self.error
        return PDF, self.disposicion


class QuotingFake:
    def __init__(self) -> None:
        self.error: QuotingEngineGatewayError | None = None

    async def listar_productos(self):
        if self.error:
            raise self.error
        return CATALOGO


@pytest.fixture
async def client():
    policies, quoting = PoliciesFake(), QuotingFake()
    app.dependency_overrides[get_insurancepolicies_service_gateway] = lambda: policies
    app.dependency_overrides[get_quotingengine_service_gateway] = lambda: quoting
    app.dependency_overrides[get_cliente_id] = lambda: CLIENTE_ID
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http, policies, quoting
    app.dependency_overrides.clear()


async def test_sin_token_es_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        response = await http.get(BASE)

    assert response.status_code == 401
    assert response.json()["codigo"] == "NO_AUTENTICADO"


async def test_lista_resuelve_nombres_y_usa_el_cliente_del_token(client):
    http, policies, _ = client

    response = await http.get(BASE, headers={"X-Correlation-Id": "corr-1"})

    assert response.status_code == 200
    assert policies.llamadas == [("listar", CLIENTE_ID, "corr-1")]
    poliza = response.json()["polizas"][0]
    assert poliza["producto"] == {"codigo": "SEGURO_VIDA_HIPOTECARIO", "nombre": "Seguro de vida hipotecario"}
    assert [c["nombre"] for c in poliza["coberturas"]] == ["Muerte por cualquier causa", None]
    assert response.json()["sincronizado_en"]


async def test_lista_no_expone_historial_ni_ids_internos(client):
    http, _, _ = client

    poliza = (await http.get(BASE)).json()["polizas"][0]

    assert "historial" not in poliza
    assert "cliente_id" not in poliza and "cotizacion_id" not in poliza
    assert "prima" not in poliza["coberturas"][0]


async def test_catalogo_caido_no_rompe_la_lista(client):
    http, _, quoting = client
    quoting.error = QuotingEngineGatewayError(503, "caído")

    response = await http.get(BASE)

    assert response.status_code == 200
    poliza = response.json()["polizas"][0]
    assert poliza["producto"] is None
    assert all(c["nombre"] is None for c in poliza["coberturas"])


async def test_lista_vacia(client):
    http, policies, _ = client
    policies.polizas = []

    response = await http.get(BASE)

    assert response.status_code == 200
    assert response.json()["polizas"] == []


@pytest.mark.parametrize("status_servicio,esperado", [(404, 404), (500, 503), (503, 503)])
async def test_errores_de_ms_polizas_se_traducen(client, status_servicio, esperado):
    http, policies, _ = client
    policies.error = PoliciesGatewayError(status_servicio, "detalle interno")

    response = await http.get(BASE)

    assert response.status_code == esperado
    cuerpo = response.json()
    assert set(cuerpo) == {"codigo", "mensaje", "correlation_id"}
    assert "detalle interno" not in json.dumps(cuerpo)


async def test_certificado_devuelve_pdf(client):
    http, policies, _ = client

    response = await http.get(f"{BASE}/{POLIZA_ID}/certificado/descarga", headers={"X-Correlation-Id": "c2"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == PDF
    assert response.headers["content-disposition"] == 'attachment; filename="certificado-SLV-2026-08341.pdf"'
    assert policies.llamadas == [("certificado", POLIZA_ID, CLIENTE_ID, "c2")]


async def test_certificado_descarta_disposicion_insegura(client):
    http, policies, _ = client
    policies.disposicion = 'attachment; filename="../../etc/passwd"'

    response = await http.get(f"{BASE}/{POLIZA_ID}/certificado/descarga")

    assert response.headers["content-disposition"] == 'attachment; filename="certificado-poliza.pdf"'


@pytest.mark.parametrize("status_servicio", [403, 404, 409])
async def test_certificado_propaga_errores_de_cliente(client, status_servicio):
    http, policies, _ = client
    policies.error = PoliciesGatewayError(status_servicio, "x")

    response = await http.get(f"{BASE}/{POLIZA_ID}/certificado/descarga")

    assert response.status_code == status_servicio


async def test_certificado_con_id_invalido_es_422(client):
    http, _, _ = client

    response = await http.get(f"{BASE}/no-es-uuid/certificado/descarga")

    assert response.status_code == 422


async def test_la_respuesta_cumple_la_muestra_del_contrato(client):
    http, _, _ = client
    muestra = json.loads(CONTRATO.read_text(encoding="utf-8"))

    cuerpo = (await http.get(BASE)).json()

    assert set(cuerpo) == set(muestra)
    assert set(cuerpo["polizas"][0]) == set(muestra["polizas"][0])
    assert set(cuerpo["polizas"][0]["coberturas"][0]) == set(muestra["polizas"][0]["coberturas"][0])
    assert cuerpo["polizas"][0]["prima_total"] == muestra["polizas"][0]["prima_total"]
