import json
import uuid
from datetime import date

import httpx
import pytest

from src.application.ports.polizas import PolizasNoDisponibles
from src.core.config import Settings
from src.infrastructure.gateways.http_polizas_client import HttpPolizasClient, limpiar_cache_productos
from src.infrastructure.gateways.polizas_en_memoria import PolizasEnMemoria
from src.infrastructure.gateways.polizas_factory import crear_polizas_port

CLIENTE = uuid.UUID("11111111-1111-4111-8111-111111111111")
POLIZA = uuid.UUID("8d2b6c1e-4a7f-4f0e-9a51-0c6b1d9e2f10")
PRODUCTO = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000001")


def _poliza_json(**cambios) -> dict:
    """Forma real de `PolizaResponse` de MS Pólizas."""
    datos = {
        "poliza_id": str(POLIZA),
        "cliente_id": str(CLIENTE),
        "cotizacion_id": str(uuid.uuid4()),
        "producto_id": str(PRODUCTO),
        "numero": "POL-2026-000123",
        "estado": "EMITIDA",
        "vigencia_desde": "2026-03-12T00:00:00Z",
        "vigencia_hasta": "2027-03-12T00:00:00Z",
        "emitida_en": "2026-03-12T00:00:00Z",
        "ramo": "VIAJES",
        "prima_total": "52000.00",
        "coberturas": [],
        "documento_url": None,
    }
    datos.update(cambios)
    return datos


PRODUCTOS = [
    {"producto_id": str(PRODUCTO), "codigo": "SEGURO_VIAJE", "nombre": "Seguro de viaje", "ramo": "VIAJES"},
    {"producto_id": str(uuid.uuid4()), "codigo": "VIDA_HIPOTECARIO", "nombre": "Vida", "ramo": "VIDA"},
]


@pytest.fixture(autouse=True)
def cache_limpia():
    limpiar_cache_productos()
    yield
    limpiar_cache_productos()


def _cliente(handler) -> HttpPolizasClient:
    return HttpPolizasClient("http://polizas", "http://cotizacion", transport=httpx.MockTransport(handler))


def _servicios(polizas_handler, productos=PRODUCTOS, llamadas=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if llamadas is not None:
            llamadas.append((request.url.host, request.url.path, dict(request.headers)))
        if request.url.host == "cotizacion":
            return httpx.Response(200, json=productos)
        return polizas_handler(request)

    return handler


async def test_lista_las_polizas_con_el_producto_del_catalogo():
    llamadas = []

    polizas = await _cliente(_servicios(lambda r: httpx.Response(200, json=[_poliza_json()]), llamadas=llamadas)).listar_por_cliente(
        CLIENTE, "corr-1"
    )

    host, path, headers = llamadas[0]
    assert (host, path) == ("polizas", "/api/v1/insurancepolicies-service/polizas/mis-polizas")
    assert headers["x-client-id"] == str(CLIENTE) and headers["x-correlation-id"] == "corr-1"
    assert llamadas[1][:2] == ("cotizacion", "/api/v1/quotingengine-service/productos")
    [poliza] = polizas
    assert (poliza.producto_codigo, poliza.producto_nombre) == ("SEGURO_VIAJE", "Seguro de viaje")
    assert (poliza.estado, poliza.numero) == ("EMITIDA", "POL-2026-000123")
    assert (poliza.vigencia_desde, poliza.vigencia_hasta) == (date(2026, 3, 12), date(2027, 3, 12))


async def test_el_catalogo_de_productos_se_guarda_en_cache():
    llamadas = []
    cliente = _cliente(_servicios(lambda r: httpx.Response(200, json=[_poliza_json()]), llamadas=llamadas))

    await cliente.listar_por_cliente(CLIENTE, "c")
    await cliente.listar_por_cliente(CLIENTE, "c")

    assert sum(1 for host, *_ in llamadas if host == "cotizacion") == 1


async def test_producto_desconocido_queda_sin_codigo():
    polizas = await _cliente(
        _servicios(lambda r: httpx.Response(200, json=[_poliza_json(producto_id=str(uuid.uuid4()))]))
    ).listar_por_cliente(CLIENTE, "c")

    assert polizas[0].producto_codigo == ""


async def test_obtener_propia_ajena_e_inexistente():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(str(POLIZA)):
            if request.headers["x-client-id"] != str(CLIENTE):
                return httpx.Response(403, json={"detail": "No puedes consultar esta póliza."})
            return httpx.Response(200, json=_poliza_json())
        return httpx.Response(404, json={"detail": "Póliza no encontrada."})

    cliente = _cliente(_servicios(handler))

    assert (await cliente.obtener(POLIZA, CLIENTE, "c")).numero == "POL-2026-000123"
    assert await cliente.obtener(POLIZA, uuid.uuid4(), "c") is None
    assert await cliente.obtener(uuid.uuid4(), CLIENTE, "c") is None


@pytest.mark.parametrize(
    "respuesta",
    [
        httpx.Response(500),
        httpx.Response(200, text="no es json"),
        httpx.Response(200, json=[{"numero": "incompleta"}]),
        httpx.Response(200, json={"no": "es lista"}),
    ],
)
async def test_errores_y_respuestas_invalidas_son_no_disponible(respuesta):
    with pytest.raises(PolizasNoDisponibles):
        await _cliente(_servicios(lambda request: respuesta)).listar_por_cliente(CLIENTE, "c")


async def test_catalogo_de_productos_caido_es_no_disponible():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "cotizacion":
            return httpx.Response(503)
        return httpx.Response(200, json=[_poliza_json()])

    with pytest.raises(PolizasNoDisponibles):
        await _cliente(handler).listar_por_cliente(CLIENTE, "c")


async def test_timeout_es_no_disponible():
    def handler(request):
        raise httpx.ConnectTimeout("timeout", request=request)

    with pytest.raises(PolizasNoDisponibles):
        await _cliente(handler).obtener(POLIZA, CLIENTE, "c")


async def test_en_memoria_asigna_las_polizas_comodin_a_cada_cliente():
    adaptador = PolizasEnMemoria.desde_archivo()
    otro = uuid.uuid4()

    del_cliente = await adaptador.listar_por_cliente(CLIENTE, "c")
    del_otro = await adaptador.listar_por_cliente(otro, "c")

    assert {p.numero for p in del_cliente} == {p.numero for p in del_otro}
    assert {p.poliza_id for p in del_cliente}.isdisjoint({p.poliza_id for p in del_otro})
    poliza = del_cliente[0]
    assert (await adaptador.obtener(poliza.poliza_id, CLIENTE, "c")).cliente_id == CLIENTE
    assert await adaptador.obtener(poliza.poliza_id, otro, "c") is None


async def test_en_memoria_respeta_un_cliente_fijo(tmp_path):
    archivo = tmp_path / "semilla.json"
    plantilla = {
        "poliza_id": str(POLIZA), "cliente_id": str(CLIENTE), "numero": "SLV-1", "estado": "EMITIDA",
        "producto_codigo": "SEGURO_VIAJE", "producto_nombre": "Seguro de viaje",
        "vigencia_desde": "2026-03-12", "vigencia_hasta": "2027-03-12",
    }
    archivo.write_text(json.dumps({"polizas": [plantilla]}), encoding="utf-8")
    adaptador = PolizasEnMemoria.desde_archivo(archivo)

    assert (await adaptador.obtener(POLIZA, CLIENTE, "c")).cliente_id == CLIENTE
    assert await adaptador.listar_por_cliente(uuid.uuid4(), "c") == []


def test_factory_elige_el_adaptador_por_configuracion():
    assert isinstance(crear_polizas_port(Settings(POLIZAS_ADAPTER="memoria")), PolizasEnMemoria)
    assert isinstance(crear_polizas_port(Settings(POLIZAS_ADAPTER="http")), HttpPolizasClient)
