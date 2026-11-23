import httpx
import pytest

from src.infrastructure.gateways.insurancepolicies_service_gateway import (
    InsurancePoliciesServiceGateway,
    PoliciesGatewayError,
)

CLIENTE_ID = "11111111-1111-4111-8111-111111111111"
POLIZA_ID = "8d2b6c1e-4a7f-4f0e-9a51-0c6b1d9e2f10"
PREFIJO = "/api/v1/insurancepolicies-service/polizas"


def _gateway(handler) -> InsurancePoliciesServiceGateway:
    return InsurancePoliciesServiceGateway(
        base_url="http://polizas", transport=httpx.MockTransport(handler), timeout_seconds=1
    )


async def test_lista_envia_cliente_y_correlacion():
    vistos = {}

    def handler(request: httpx.Request) -> httpx.Response:
        vistos["path"] = request.url.path
        vistos["cliente"] = request.headers["X-Client-Id"]
        vistos["correlacion"] = request.headers["X-Correlation-Id"]
        return httpx.Response(200, json=[{"poliza_id": POLIZA_ID}])

    polizas = await _gateway(handler).listar_mis_polizas(CLIENTE_ID, "corr-1")

    assert polizas == [{"poliza_id": POLIZA_ID}]
    assert vistos == {"path": f"{PREFIJO}/mis-polizas", "cliente": CLIENTE_ID, "correlacion": "corr-1"}


async def test_lista_que_no_es_arreglo_es_502():
    gateway = _gateway(lambda request: httpx.Response(200, json={"polizas": []}))

    with pytest.raises(PoliciesGatewayError) as exc:
        await gateway.listar_mis_polizas(CLIENTE_ID, "c")

    assert exc.value.status_code == 502


async def test_cuerpo_no_json_es_502():
    gateway = _gateway(lambda request: httpx.Response(200, text="no json"))

    with pytest.raises(PoliciesGatewayError) as exc:
        await gateway.listar_mis_polizas(CLIENTE_ID, "c")

    assert exc.value.status_code == 502


async def test_error_de_red_es_503():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin red")

    with pytest.raises(PoliciesGatewayError) as exc:
        await _gateway(handler).listar_mis_polizas(CLIENTE_ID, "c")

    assert exc.value.status_code == 503


async def test_error_del_servicio_conserva_estado_y_detalle():
    gateway = _gateway(lambda request: httpx.Response(403, json={"detail": "No puedes consultar esta póliza."}))

    with pytest.raises(PoliciesGatewayError) as exc:
        await gateway.descargar_certificado(POLIZA_ID, CLIENTE_ID, "c")

    assert exc.value.status_code == 403
    assert exc.value.detail == "No puedes consultar esta póliza."


async def test_certificado_valido_devuelve_bytes_y_disposicion():
    gateway = _gateway(
        lambda request: httpx.Response(
            200,
            content=b"%PDF-1.4",
            headers={"content-type": "application/pdf", "content-disposition": 'attachment; filename="c.pdf"'},
        )
    )

    contenido, disposicion = await gateway.descargar_certificado(POLIZA_ID, CLIENTE_ID, "c")

    assert contenido == b"%PDF-1.4"
    assert disposicion == 'attachment; filename="c.pdf"'


async def test_certificado_que_no_es_pdf_es_502():
    gateway = _gateway(lambda request: httpx.Response(200, content=b"<html>", headers={"content-type": "text/html"}))

    with pytest.raises(PoliciesGatewayError) as exc:
        await gateway.descargar_certificado(POLIZA_ID, CLIENTE_ID, "c")

    assert exc.value.status_code == 502
