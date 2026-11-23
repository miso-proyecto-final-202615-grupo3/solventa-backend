import httpx
import pytest

from src.infrastructure.gateways.backend_gateway import BackendGatewayError, json_object
from src.infrastructure.gateways.identity_service_gateway import IdentityServiceGateway


async def test_error_de_red_se_expone_como_servicio_no_disponible():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no disponible", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        gateway = IdentityServiceGateway(client)
        with pytest.raises(BackendGatewayError) as exc:
            await gateway.validar_api_key("clave")
    assert exc.value.status_code == 503
    assert exc.value.detail == "Servicio de backend no disponible."


@pytest.mark.parametrize(
    "response",
    [httpx.Response(200, text="no es JSON"), httpx.Response(200, json=[])],
)
def test_json_de_autorizacion_invalido_se_expone_como_error_del_backend(response):
    with pytest.raises(BackendGatewayError) as exc:
        json_object(response)
    assert exc.value.status_code == 502


def test_error_de_autorizacion_conserva_estado_y_detalle():
    detail = {"codigo": "NO_AUTORIZADO"}
    with pytest.raises(BackendGatewayError) as exc:
        json_object(httpx.Response(403, json={"detail": detail}))
    assert exc.value.status_code == 403
    assert exc.value.detail == detail
