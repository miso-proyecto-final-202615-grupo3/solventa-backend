import json
import logging
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from src.infrastructure.gateways.insuranceclaims_service_gateway import ClaimsGatewayError
from src.main import app
from src.presentation.dependencies import get_cliente_id, get_insuranceclaims_service_gateway

CONTRACTS = Path(__file__).resolve().parents[3] / "docs" / "contracts" / "evidencias"
BASE = "/api/v1/bff-mobile/siniestros"
SINIESTRO_ID = "c41f0e2a-9b7d-4e55-8a0c-2f6d1b3e9a77"
EVIDENCIA_ID = "5e0c2d8a-1f43-4b7e-9c0d-6a2b8e4f1c33"
CLIENTE_ID = "11111111-1111-4111-8111-111111111111"


def _muestra(nombre: str) -> dict:
    return json.loads((CONTRACTS / nombre).read_text(encoding="utf-8"))


class ClaimsFake:
    def __init__(self) -> None:
        self.llamadas: list[tuple] = []
        self.error: ClaimsGatewayError | None = None
        self.claves: list[str | None] = []
        self.status = 201

    async def solicitar_carga_evidencia(self, cliente_id, siniestro_id, payload, correlation_id, idempotency_key=None):
        self.llamadas.append(("solicitar", cliente_id, siniestro_id, payload, correlation_id))
        self.claves.append(idempotency_key)
        if self.error:
            raise self.error
        return self.status, _muestra("solicitud-response.json")

    async def confirmar_carga_evidencia(self, cliente_id, siniestro_id, evidencia_id, correlation_id):
        self.llamadas.append(("confirmar", cliente_id, siniestro_id, evidencia_id))
        if self.error:
            raise self.error
        return _muestra("confirmacion-response.json")

    async def registrar_ubicacion(self, cliente_id, siniestro_id, payload, correlation_id):
        self.llamadas.append(("ubicacion", cliente_id, siniestro_id, payload))
        if self.error:
            raise self.error
        return _muestra("ubicacion-response.json")

    async def obtener_siniestro(self, cliente_id, siniestro_id, correlation_id):
        return _muestra("detalle-con-evidencias.json")


@pytest.fixture
async def client():
    claims = ClaimsFake()
    app.dependency_overrides[get_insuranceclaims_service_gateway] = lambda: claims
    app.dependency_overrides[get_cliente_id] = lambda: CLIENTE_ID
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http, claims
    app.dependency_overrides.clear()


async def test_solicitar_reenvia_y_devuelve_la_carga_sin_cambios(client, caplog):
    http, claims = client
    caplog.set_level(logging.DEBUG, logger="uvicorn.error")

    response = await http.post(
        f"{BASE}/{SINIESTRO_ID}/evidencias", json=_muestra("solicitud-request.json"), headers={"X-Correlation-Id": "c-1"}
    )

    assert response.status_code == 201
    esperado = _muestra("solicitud-response.json")
    assert response.json()["carga"]["campos"] == esperado["carga"]["campos"]
    _, cliente, siniestro, payload, corr = claims.llamadas[0]
    assert (cliente, siniestro, corr) == (CLIENTE_ID, SINIESTRO_ID, "c-1")
    assert payload["tipo"] == "FOTO" and payload["capturada_en"] == "2026-11-10T14:35:00-05:00"
    assert "x-amz-signature" not in caplog.text and esperado["carga"]["campos"]["policy"] not in caplog.text


async def test_confirmar_y_ubicacion(client):
    http, claims = client

    confirmada = await http.post(f"{BASE}/{SINIESTRO_ID}/evidencias/{EVIDENCIA_ID}/confirmacion")
    ubicacion = await http.put(f"{BASE}/{SINIESTRO_ID}/ubicacion", json=_muestra("ubicacion-request.json"))

    assert confirmada.json()["estado"] == "CARGADA"
    assert ubicacion.json()["ubicacion"]["fuente"] == "GPS"
    assert claims.llamadas[1][3]["latitud"] == 4.6533


async def test_detalle_con_evidencias(client):
    http, _ = client

    response = await http.get(f"{BASE}/{SINIESTRO_ID}")

    cuerpo = response.json()
    assert [e["estado"] for e in cuerpo["evidencias"]] == ["CARGADA", "PENDIENTE"]
    assert cuerpo["ubicacion"]["precision_m"] == 18.5


@pytest.mark.parametrize(
    "body",
    [
        {**_muestra("solicitud-request.json"), "tipo": "AUDIO"},
        {**_muestra("solicitud-request.json"), "tamano_bytes": 0},
        {**_muestra("solicitud-request.json"), "url": "https://otro"},
    ],
)
async def test_validacion_de_la_solicitud(client, body):
    http, claims = client

    assert (await http.post(f"{BASE}/{SINIESTRO_ID}/evidencias", json=body)).status_code == 422
    assert claims.llamadas == []


@pytest.mark.parametrize("cambios", [{"latitud": 91}, {"precision_m": 0}, {"fuente": "SATELITE"}])
async def test_validacion_de_la_ubicacion(client, cambios):
    http, _ = client

    response = await http.put(f"{BASE}/{SINIESTRO_ID}/ubicacion", json={**_muestra("ubicacion-request.json"), **cambios})

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("status", "codigo"),
    [(409, "LIMITE_EVIDENCIAS"), (413, "EVIDENCIA_DEMASIADO_GRANDE"), (415, "FORMATO_NO_SOPORTADO"),
     (422, "EVIDENCIA_RECHAZADA"), (409, "CARGA_EXPIRADA")],
)
async def test_traduce_errores(client, status, codigo):
    http, claims = client
    claims.error = ClaimsGatewayError(status, {"codigo": codigo, "mensaje": "x"})

    response = await http.post(f"{BASE}/{SINIESTRO_ID}/evidencias/{EVIDENCIA_ID}/confirmacion")

    assert response.status_code == status
    assert response.json()["codigo"] == codigo


async def test_solicitar_reenvia_la_idempotency_key_y_el_200_del_reintento(client):
    http, claims = client
    claims.status = 200
    clave = "0b8f6c1e-2a4d-4f6e-8c1b-9d3e5a7f2b40"

    response = await http.post(
        f"{BASE}/{SINIESTRO_ID}/evidencias", json=_muestra("solicitud-request.json"), headers={"Idempotency-Key": clave}
    )
    invalida = await http.post(
        f"{BASE}/{SINIESTRO_ID}/evidencias", json=_muestra("solicitud-request.json"), headers={"Idempotency-Key": "x"}
    )

    assert response.status_code == 200 and claims.claves == [clave]
    assert invalida.status_code == 400 and invalida.json()["codigo"] == "DATOS_INVALIDOS"


async def test_solicitar_ya_cargada_devuelve_carga_null(client):
    http, claims = client
    claims.status = 200
    cargada = {**_muestra("solicitud-response.json"), "estado": "CARGADA", "carga": None}
    claims.solicitar_carga_evidencia = lambda *a, **k: _async((200, cargada))

    response = await http.post(f"{BASE}/{SINIESTRO_ID}/evidencias", json=_muestra("solicitud-request.json"))

    assert response.status_code == 200 and response.json()["carga"] is None


async def _async(valor):
    return valor
