import pytest
import httpx
from httpx import ASGITransport, AsyncClient

from src.infrastructure.gateways.quotingengine_service_gateway import (
    QuotingEngineGatewayError,
    QuotingEngineServiceGateway,
)
from src.main import app
from src.presentation.dependencies import get_quotingengine_service_gateway

BASE_PATH = "/api/v1/bff-web"
PRODUCTO = {"codigo": "auto"}
COTIZACION = {"cotizacion_id": "95b19edf-6c4b-4437-99db-d84d0ef482fc"}
PAYLOAD = b'{"cliente_id":"cliente-1","producto_codigo":"auto","parametros":{}}'
CONDICIONES = {
    "condiciones_cotizacion_id": "5a84beea-6422-4c0c-89e7-5e5e0cbac68d",
    "cotizacion_id": COTIZACION["cotizacion_id"],
    "version_condiciones_generales": "1.0",
    "condiciones_generales": "Condiciones",
    "condiciones_particulares": {
        "moneda": "COP",
        "prima_total": "100.00",
        "vigencia_propuesta": {
            "desde": "2026-01-01T00:00:00Z",
            "hasta": "2027-01-01T00:00:00Z",
        },
        "coberturas": [{"prima": "100.00", "limite_asegurado": "1000.00", "deducible": "0.00"}],
    },
    "creada_en": "2026-01-01T00:00:00Z",
    "ultima_decision": None,
}
DECISION = {
    "decision_condiciones_id": "6e1d4e4e-2b46-4c5f-bb07-d84daec7ab50",
    "condiciones_cotizacion_id": CONDICIONES["condiciones_cotizacion_id"],
    "cliente_id": "d0af9a19-872e-4e16-bc56-e8217d4ff024",
    "version_condiciones_generales": "1.0",
    "decision": "ACEPTADA",
    "decidida_en": "2026-01-01T00:00:00Z",
}
DECISION_PAYLOAD = (
    b'{"condiciones_cotizacion_id":"5a84beea-6422-4c0c-89e7-5e5e0cbac68d",'
    b'"decision":"ACEPTADA"}'
)


class FakeQuotingEngineGateway:
    def __init__(self):
        self.calls: list[tuple] = []
        self.error: tuple[int, str] | None = None

    def _check_error(self) -> None:
        if self.error:
            raise QuotingEngineGatewayError(*self.error)

    async def listar_productos(self):
        self.calls.append(("listar_productos",))
        self._check_error()
        return [PRODUCTO]

    async def obtener_producto(self, codigo: str):
        self.calls.append(("obtener_producto", codigo))
        self._check_error()
        return PRODUCTO

    async def solicitar_cotizacion(self, payload: bytes, content_type: str):
        self.calls.append(("solicitar_cotizacion", payload, content_type))
        self._check_error()
        return COTIZACION

    async def obtener_cotizacion(self, cotizacion_id: str):
        self.calls.append(("obtener_cotizacion", cotizacion_id))
        self._check_error()
        return COTIZACION

    async def obtener_condiciones(self, cotizacion_id: str):
        self.calls.append(("obtener_condiciones", cotizacion_id))
        self._check_error()
        return CONDICIONES

    async def registrar_decision_condiciones(
        self, cotizacion_id: str, payload: bytes, content_type: str
    ):
        self.calls.append(
            ("registrar_decision_condiciones", cotizacion_id, payload, content_type)
        )
        self._check_error()
        return DECISION


@pytest.fixture
async def bff_client():
    gateway = FakeQuotingEngineGateway()
    app.dependency_overrides[get_quotingengine_service_gateway] = lambda: gateway
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, gateway
    app.dependency_overrides.clear()


async def test_expone_y_reenvia_las_operaciones_de_cotizacion(bff_client):
    client, gateway = bff_client

    listado = await client.get(f"{BASE_PATH}/productos")
    producto = await client.get(f"{BASE_PATH}/productos/auto")
    nueva = await client.post(
        f"{BASE_PATH}/cotizaciones",
        content=PAYLOAD,
        headers={"content-type": "application/vnd.api+json"},
    )
    obtenida = await client.get(f"{BASE_PATH}/cotizaciones/{COTIZACION['cotizacion_id']}")

    assert listado.status_code == 200
    assert listado.json() == [PRODUCTO]
    assert producto.json() == PRODUCTO
    assert nueva.status_code == 201
    assert nueva.json() == COTIZACION
    assert obtenida.json() == COTIZACION
    assert gateway.calls == [
        ("listar_productos",),
        ("obtener_producto", "auto"),
        (
            "solicitar_cotizacion",
            PAYLOAD,
            "application/vnd.api+json",
        ),
        ("obtener_cotizacion", COTIZACION["cotizacion_id"]),
    ]


async def test_expone_error_del_servicio_de_cotizacion(bff_client):
    client, gateway = bff_client
    gateway.error = (404, "Cotización no encontrada.")

    response = await client.get(f"{BASE_PATH}/cotizaciones/{COTIZACION['cotizacion_id']}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Cotización no encontrada."


async def test_expone_condiciones_y_registra_decision(bff_client):
    client, gateway = bff_client
    url = f"{BASE_PATH}/cotizaciones/{COTIZACION['cotizacion_id']}/condiciones"

    consulta = await client.get(url)
    decision = await client.post(
        f"{url}/decisiones",
        content=DECISION_PAYLOAD,
        headers={"content-type": "application/vnd.api+json"},
    )

    assert consulta.status_code == 200
    assert consulta.json() == CONDICIONES
    assert decision.status_code == 201
    assert decision.json() == DECISION
    assert gateway.calls == [
        ("obtener_condiciones", COTIZACION["cotizacion_id"]),
        (
            "registrar_decision_condiciones",
            COTIZACION["cotizacion_id"],
            DECISION_PAYLOAD,
            "application/vnd.api+json",
        ),
    ]


async def test_decision_reenvia_content_type_por_defecto(bff_client):
    client, gateway = bff_client
    response = await client.post(
        f"{BASE_PATH}/cotizaciones/{COTIZACION['cotizacion_id']}/condiciones/decisiones",
        content=DECISION_PAYLOAD,
    )
    assert response.status_code == 201
    assert gateway.calls == [
        ("registrar_decision_condiciones", COTIZACION["cotizacion_id"], DECISION_PAYLOAD, "application/json")
    ]


@pytest.mark.parametrize(
    ("metodo", "sufijo", "codigo"),
    [
        ("GET", "", 404),
        ("GET", "", 503),
        ("POST", "/decisiones", 404),
        ("POST", "/decisiones", 409),
        ("POST", "/decisiones", 422),
        ("POST", "/decisiones", 503),
    ],
)
async def test_condiciones_propaga_errores_del_servicio(bff_client, metodo, sufijo, codigo):
    client, gateway = bff_client
    gateway.error = (codigo, "Error de cotización.")
    response = await client.request(
        metodo,
        f"{BASE_PATH}/cotizaciones/{COTIZACION['cotizacion_id']}/condiciones{sufijo}",
        content=DECISION_PAYLOAD if metodo == "POST" else None,
    )
    assert response.status_code == codigo
    assert response.json()["detail"] == "Error de cotización."


@pytest.mark.parametrize(("metodo", "sufijo"), [("GET", ""), ("POST", "/decisiones")])
async def test_condiciones_rechaza_cotizacion_id_invalido(bff_client, metodo, sufijo):
    client, gateway = bff_client
    response = await client.request(
        metodo,
        f"{BASE_PATH}/cotizaciones/no-es-uuid/condiciones{sufijo}",
        content=DECISION_PAYLOAD if metodo == "POST" else None,
    )
    assert response.status_code == 422
    assert gateway.calls == []


async def test_ruta_y_gateway_reenvian_respuesta_422_estructurada(bff_client):
    client, _ = bff_client
    detalle = [{"loc": ["body", "decision"], "msg": "Decisión inválida"}]
    llamadas: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        llamadas.append(request)
        return httpx.Response(422, json={"detail": detalle})

    gateway = QuotingEngineServiceGateway(
        base_url="http://quotingengine-host:8000",
        transport=httpx.MockTransport(handler),
    )
    app.dependency_overrides[get_quotingengine_service_gateway] = lambda: gateway
    try:
        response = await client.post(
            f"{BASE_PATH}/cotizaciones/{COTIZACION['cotizacion_id']}/condiciones/decisiones",
            content=DECISION_PAYLOAD,
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 422
        assert response.json() == {"detail": detalle}
        assert llamadas[0].url.path == (
            f"/api/v1/quotingengine-service/cotizaciones/{COTIZACION['cotizacion_id']}"
            "/condiciones/decisiones"
        )
        assert llamadas[0].content == DECISION_PAYLOAD
    finally:
        await gateway.aclose()
