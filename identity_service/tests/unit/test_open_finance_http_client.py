import uuid
from decimal import Decimal

import httpx
import pytest

from src.application.ports.open_finance import OpenFinanceNoDisponibleError
from src.infrastructure.gateways.open_finance_http_client import OpenFinanceHttpClient


async def test_consulta_perfil_financiero_del_proveedor():
    cliente_id = uuid.uuid4()
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "ingreso_mensual": 8500000,
                "ahorros_liquidos": 25500000,
                "dti_pct": 28,
                "sobregiros_12_meses": 0,
                "score": 820,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        perfil = await OpenFinanceHttpClient(
            client, "http://openfinance"
        ).obtener_perfil(cliente_id)

    assert requests[0].url == "http://openfinance/profile"
    assert requests[0].read() == f'{{"cliente_id":"{cliente_id}"}}'.encode()
    assert perfil.ingreso_mensual == Decimal("8500000")
    assert perfil.ahorros_liquidos == Decimal("25500000")
    assert perfil.dti_pct == Decimal("28")
    assert perfil.score == 820


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503),
        httpx.Response(200, json={"ingreso_mensual": -1}),
        httpx.Response(200, text="not-json"),
    ],
)
async def test_indisponibilidad_o_respuesta_invalida_se_normaliza(response):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: response)
    ) as client:
        with pytest.raises(OpenFinanceNoDisponibleError):
            await OpenFinanceHttpClient(client, "http://openfinance").obtener_perfil(
                uuid.uuid4()
            )
