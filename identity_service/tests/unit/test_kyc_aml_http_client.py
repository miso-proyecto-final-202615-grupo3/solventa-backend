import uuid

import httpx
import pytest

from src.application.ports.kyc_aml import ProveedorKycAmlError
from src.domain.verificaciones_kyc_aml.entities import (
    ArchivoDocumento,
    ResultadoChequeo,
    RutasDocumentos,
)
from src.infrastructure.gateways.kyc_aml_http_client import KycAmlHttpClient

JPEG = ArchivoDocumento(b"\xff\xd8\xff-datos", "image/jpeg")
RUTAS = RutasDocumentos("s3://b/frontal.jpg", "s3://b/reverso.jpg")


def _cliente(handler) -> KycAmlHttpClient:
    return KycAmlHttpClient(base_url="http://kyc", transport=httpx.MockTransport(handler))


async def test_iniciar_envia_documentos_y_referencias_s3():
    capturado = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capturado["request"] = request
        return httpx.Response(200, json={"verification_id": "ext-1"})

    cliente_id, verificacion_id = uuid.uuid4(), uuid.uuid4()
    inicio = await _cliente(handler).iniciar_verificacion(
        cliente_id, verificacion_id, RUTAS, JPEG, JPEG, "corr-1"
    )

    request = capturado["request"]
    cuerpo = request.read()
    assert request.method == "POST"
    assert request.url.path == "/verificaciones-kyc-aml"
    assert request.headers["x-correlation-id"] == "corr-1"
    assert request.headers["content-type"].startswith("multipart/form-data")
    assert b's3://b/frontal.jpg' in cuerpo and str(cliente_id).encode() in cuerpo
    assert b'name="documento_frontal"' in cuerpo and b'name="documento_reverso"' in cuerpo
    assert inicio.verificacion_externa_id == "ext-1"
    assert inicio.respuesta == {"verification_id": "ext-1"}


@pytest.mark.parametrize(
    ("kyc", "aml", "esperado"),
    [
        ("PASSED", "FAILED", (ResultadoChequeo.APROBADO, ResultadoChequeo.RECHAZADO)),
        ("PENDING", "PASSED", (ResultadoChequeo.PENDIENTE, ResultadoChequeo.APROBADO)),
        ("raro", None, (ResultadoChequeo.PENDIENTE, ResultadoChequeo.PENDIENTE)),
    ],
)
async def test_consultar_mapea_resultados_por_separado(kyc, aml, esperado):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/verificaciones-kyc-aml/ext-1"
        return httpx.Response(
            200, json={"verification_id": "ext-1", "kyc_status": kyc, "aml_status": aml}
        )

    resultado = await _cliente(handler).consultar_resultado("ext-1", "corr")

    assert (resultado.kyc, resultado.aml) == esperado


@pytest.mark.parametrize(
    ("respuesta", "codigo"),
    [
        (httpx.Response(500, json={}), "PROVEEDOR_HTTP_500"),
        (httpx.Response(200, text="no-json"), "RESPUESTA_INVALIDA"),
        (httpx.Response(200, json=["x"]), "RESPUESTA_INVALIDA"),
        (httpx.Response(200, json={}), "RESPUESTA_INVALIDA"),
    ],
)
async def test_iniciar_falla_con_respuestas_invalidas(respuesta, codigo):
    cliente = _cliente(lambda request: respuesta)

    with pytest.raises(ProveedorKycAmlError) as exc:
        await cliente.iniciar_verificacion(uuid.uuid4(), uuid.uuid4(), RUTAS, JPEG, JPEG, "c")

    assert exc.value.codigo == codigo


async def test_error_de_red_se_convierte_en_error_del_proveedor():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout")

    with pytest.raises(ProveedorKycAmlError) as exc:
        await _cliente(handler).consultar_resultado("ext-1", "c")

    assert exc.value.codigo == "PROVEEDOR_NO_DISPONIBLE"
