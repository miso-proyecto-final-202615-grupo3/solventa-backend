import pytest
from httpx import ASGITransport, AsyncClient

from src.infrastructure.gateways.quotingengine_service_gateway import (
    QuotingEngineGatewayError,
)
from src.main import app
from src.presentation.dependencies import get_quotingengine_service_gateway

BASE_PATH = "/api/v1/bff-web"
PRODUCTO = {"codigo": "auto"}
COTIZACION = {"cotizacion_id": "95b19edf-6c4b-4437-99db-d84d0ef482fc"}
PAYLOAD = b'{"cliente_id":"cliente-1","producto_codigo":"auto","parametros":{}}'


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
