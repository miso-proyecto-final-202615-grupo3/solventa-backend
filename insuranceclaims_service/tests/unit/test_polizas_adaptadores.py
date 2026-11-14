import json
import uuid
from datetime import date

import httpx
import pytest

from src.application.ports.polizas import PolizasNoDisponibles
from src.core.config import Settings
from src.infrastructure.gateways.http_polizas_client import HttpPolizasClient
from src.infrastructure.gateways.polizas_en_memoria import PolizasEnMemoria
from src.infrastructure.gateways.polizas_factory import crear_polizas_port

CLIENTE = uuid.UUID("11111111-1111-4111-8111-111111111111")
POLIZA = uuid.UUID("8d2b6c1e-4a7f-4f0e-9a51-0c6b1d9e2f10")


def _poliza_json(**cambios) -> dict:
    datos = {
        "poliza_id": str(POLIZA),
        "cliente_id": str(CLIENTE),
        "numero": "SLV-2026-08341",
        "estado": "VIGENTE",
        "producto_codigo": "SEGURO_VIAJE",
        "producto_nombre": "Seguro de viaje",
        "vigencia_desde": "2026-03-12T00:00:00Z",
        "vigencia_hasta": "2027-03-12",
        "otro_campo": "se ignora",
    }
    datos.update(cambios)
    return datos


def _cliente(handler) -> HttpPolizasClient:
    return HttpPolizasClient("http://polizas", transport=httpx.MockTransport(handler))


async def test_lista_las_polizas_del_cliente_y_propaga_la_correlacion():
    recibido = {}

    def handler(request: httpx.Request) -> httpx.Response:
        recibido["path"] = request.url.path
        recibido["cliente"] = request.url.params["cliente_id"]
        recibido["corr"] = request.headers["X-Correlation-Id"]
        return httpx.Response(200, json={"polizas": [_poliza_json()]})

    polizas = await _cliente(handler).listar_por_cliente(CLIENTE, "corr-1")

    assert recibido == {
        "path": "/api/v1/insurancepolicies-service/polizas",
        "cliente": str(CLIENTE),
        "corr": "corr-1",
    }
    assert polizas[0].poliza_id == POLIZA
    assert polizas[0].vigencia_desde == date(2026, 3, 12)
    assert polizas[0].vigencia_hasta == date(2027, 3, 12)


async def test_obtener_una_poliza_y_404_es_none():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(str(POLIZA)):
            return httpx.Response(200, json=_poliza_json())
        return httpx.Response(404, json={"detail": "no existe"})

    cliente = _cliente(handler)

    assert (await cliente.obtener(POLIZA, "c")).numero == "SLV-2026-08341"
    assert await cliente.obtener(uuid.uuid4(), "c") is None


@pytest.mark.parametrize(
    "respuesta",
    [
        httpx.Response(500),
        httpx.Response(200, text="no es json"),
        httpx.Response(200, json={"polizas": [{"numero": "incompleta"}]}),
    ],
)
async def test_errores_y_respuestas_invalidas_son_no_disponible(respuesta):
    with pytest.raises(PolizasNoDisponibles):
        await _cliente(lambda request: respuesta).listar_por_cliente(CLIENTE, "c")


async def test_timeout_es_no_disponible():
    def handler(request):
        raise httpx.ConnectTimeout("timeout", request=request)

    with pytest.raises(PolizasNoDisponibles):
        await _cliente(handler).obtener(POLIZA, "c")


async def test_en_memoria_asigna_las_polizas_comodin_a_cada_cliente():
    adaptador = PolizasEnMemoria.desde_archivo()
    otro = uuid.uuid4()

    del_cliente = await adaptador.listar_por_cliente(CLIENTE, "c")
    del_otro = await adaptador.listar_por_cliente(otro, "c")

    assert {p.numero for p in del_cliente} == {p.numero for p in del_otro}
    assert {p.poliza_id for p in del_cliente}.isdisjoint({p.poliza_id for p in del_otro})
    poliza = del_cliente[0]
    assert (await adaptador.obtener(poliza.poliza_id, "c")).cliente_id == CLIENTE


async def test_en_memoria_respeta_un_cliente_fijo(tmp_path):
    archivo = tmp_path / "semilla.json"
    plantilla = _poliza_json(vigencia_desde="2026-03-12")
    plantilla.pop("otro_campo")
    archivo.write_text(json.dumps({"polizas": [plantilla]}), encoding="utf-8")
    adaptador = PolizasEnMemoria.desde_archivo(archivo)

    assert (await adaptador.obtener(POLIZA, "c")).cliente_id == CLIENTE
    assert await adaptador.listar_por_cliente(uuid.uuid4(), "c") == []


def test_factory_elige_el_adaptador_por_configuracion():
    assert isinstance(crear_polizas_port(Settings(POLIZAS_ADAPTER="memoria")), PolizasEnMemoria)
    assert isinstance(crear_polizas_port(Settings(POLIZAS_ADAPTER="http")), HttpPolizasClient)
