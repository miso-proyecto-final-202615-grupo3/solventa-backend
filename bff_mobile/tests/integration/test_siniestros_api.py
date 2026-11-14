import logging
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from src.infrastructure.gateways.insuranceclaims_service_gateway import ClaimsGatewayError
from src.main import app
from src.presentation.dependencies import get_cliente_id, get_insuranceclaims_service_gateway

BASE = "/api/v1/bff-mobile/siniestros"
CLIENTE_ID = "11111111-1111-4111-8111-111111111111"
POLIZA_ID = "8d2b6c1e-4a7f-4f0e-9a51-0c6b1d9e2f10"
SINIESTRO = {
    "siniestro_id": "c41f0e2a-9b7d-4e55-8a0c-2f6d1b3e9a77",
    "numero": "SIN-2026-C41F0E2A",
    "estado": "REPORTADO",
    "poliza_id": POLIZA_ID,
    "poliza_numero": "SLV-2026-08341",
    "tipo": "GASTO_MEDICO",
    "ocurrido_en": "2026-11-10T19:30:00Z",
    "reportado_en": "2026-11-10T20:02:11Z",
}
DESCRIPCION = "Me atendieron en urgencias durante el viaje."


class ClaimsFake:
    def __init__(self) -> None:
        self.llamadas: list[tuple] = []
        self.error: ClaimsGatewayError | None = None
        self.status_reporte = 201

    async def listar_polizas_elegibles(self, cliente_id, correlation_id, accept_language=None):
        self.llamadas.append(("listar", cliente_id, correlation_id, accept_language))
        if self.error:
            raise self.error
        return {"polizas": [{
            "poliza_id": POLIZA_ID, "numero": "SLV-2026-08341",
            "producto": {"codigo": "SEGURO_VIAJE", "nombre": "Seguro de viaje"},
            "vigencia_desde": "2026-03-12", "vigencia_hasta": "2027-03-12",
            "tipos_siniestro": [{"codigo": "GASTO_MEDICO", "nombre": "Gasto médico",
                                 "evidencia": {"fotos_max": 5, "videos_max": 0}}],
        }]}

    async def reportar_siniestro(self, cliente_id, idempotency_key, payload, correlation_id):
        self.llamadas.append(("reportar", cliente_id, idempotency_key, payload, correlation_id))
        if self.error:
            raise self.error
        return self.status_reporte, SINIESTRO

    async def obtener_siniestro(self, cliente_id, siniestro_id, correlation_id):
        self.llamadas.append(("obtener", cliente_id, siniestro_id, correlation_id))
        if self.error:
            raise self.error
        return SINIESTRO


@pytest.fixture
async def client():
    claims = ClaimsFake()
    app.dependency_overrides[get_insuranceclaims_service_gateway] = lambda: claims
    app.dependency_overrides[get_cliente_id] = lambda: CLIENTE_ID
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http, claims
    app.dependency_overrides.clear()


def _body(**cambios) -> dict:
    body = {"poliza_id": POLIZA_ID, "tipo": "GASTO_MEDICO", "descripcion": f"  {DESCRIPCION}  ",
            "ocurrido_en": "2026-11-10T14:30:00-05:00"}
    body.update(cambios)
    return body


async def test_sin_token_es_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        response = await http.get(f"{BASE}/polizas-elegibles")

    assert response.status_code == 401
    assert response.json()["codigo"] == "NO_AUTENTICADO"


async def test_polizas_elegibles_reenvia_cliente_correlacion_e_idioma(client):
    http, claims = client

    response = await http.get(
        f"{BASE}/polizas-elegibles", headers={"X-Correlation-Id": "corr-1", "Accept-Language": "en-US"}
    )

    assert response.status_code == 200
    assert response.json()["polizas"][0]["tipos_siniestro"][0]["codigo"] == "GASTO_MEDICO"
    assert claims.llamadas == [("listar", CLIENTE_ID, "corr-1", "en-US")]


@pytest.mark.parametrize("status_servicio", [201, 200])
async def test_reportar_propaga_201_o_200(client, status_servicio):
    http, claims = client
    claims.status_reporte = status_servicio
    key = str(uuid.uuid4())

    response = await http.post(BASE, json=_body(), headers={"Idempotency-Key": key, "X-Correlation-Id": "c-2"})

    assert response.status_code == status_servicio
    assert response.json() == SINIESTRO
    _, cliente, clave, payload, corr = claims.llamadas[0]
    assert (cliente, clave, corr) == (CLIENTE_ID, key, "c-2")
    assert payload["descripcion"] == DESCRIPCION
    assert payload["ocurrido_en"] == "2026-11-10T14:30:00-05:00"


@pytest.mark.parametrize("key", [None, "no-es-uuid"])
async def test_idempotency_key_obligatoria(client, key):
    http, claims = client
    headers = {"Idempotency-Key": key} if key else {}

    response = await http.post(BASE, json=_body(), headers=headers)

    assert response.status_code == 400
    assert response.json()["codigo"] == "DATOS_INVALIDOS"
    assert claims.llamadas == []


@pytest.mark.parametrize(
    "body",
    [
        _body(descripcion="corta"),
        _body(ocurrido_en="2026-11-10T14:30:00"),
        _body(tipo="robo"),
        {**_body(), "cliente_id": CLIENTE_ID},
        {**_body(), "correo": "ana@example.com"},
    ],
)
async def test_validacion_de_entrada(client, body):
    http, claims = client

    response = await http.post(BASE, json=body, headers={"Idempotency-Key": str(uuid.uuid4())})

    assert response.status_code == 422
    assert claims.llamadas == []


@pytest.mark.parametrize(
    ("status", "detail", "codigo"),
    [
        (404, {"codigo": "POLIZA_NO_ENCONTRADA", "mensaje": "No encontramos la póliza."}, "POLIZA_NO_ENCONTRADA"),
        (409, {"codigo": "POLIZA_NO_VIGENTE", "mensaje": "La póliza no está vigente."}, "POLIZA_NO_VIGENTE"),
        (409, {"codigo": "IDEMPOTENCIA_CONFLICTO", "mensaje": "x"}, "IDEMPOTENCIA_CONFLICTO"),
        (422, {"codigo": "TIPO_NO_PERMITIDO", "mensaje": "x"}, "TIPO_NO_PERMITIDO"),
        (500, "error interno con detalles", "SERVICIO_NO_DISPONIBLE"),
        (503, "no disponible", "SERVICIO_NO_DISPONIBLE"),
    ],
)
async def test_traduce_errores_al_formato_comun(client, status, detail, codigo):
    http, claims = client
    claims.error = ClaimsGatewayError(status, detail)

    response = await http.post(
        BASE, json=_body(), headers={"Idempotency-Key": str(uuid.uuid4()), "X-Correlation-Id": "corr-err"}
    )

    esperado = 503 if status >= 500 else status
    assert response.status_code == esperado
    assert response.json()["codigo"] == codigo
    assert response.json()["correlation_id"] == "corr-err"
    assert "detalles" not in response.json()["mensaje"]


async def test_consultar(client):
    http, claims = client

    response = await http.get(f"{BASE}/{SINIESTRO['siniestro_id']}")

    assert response.status_code == 200
    assert response.json()["numero"] == "SIN-2026-C41F0E2A"
    assert claims.llamadas[0][:3] == ("obtener", CLIENTE_ID, SINIESTRO["siniestro_id"])


async def test_consultar_con_id_invalido_es_422(client):
    http, _ = client

    assert (await http.get(f"{BASE}/no-es-uuid")).status_code == 422


async def test_no_registra_la_descripcion(client, caplog):
    http, _ = client
    caplog.set_level(logging.DEBUG)

    await http.post(BASE, json=_body(), headers={"Idempotency-Key": str(uuid.uuid4())})

    assert DESCRIPCION not in caplog.text
