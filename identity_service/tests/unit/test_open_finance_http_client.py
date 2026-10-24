import uuid
from decimal import Decimal

import httpx
import pytest

from src.infrastructure.gateways.open_finance_http_client import (
    OpenFinanceHttpClient,
    OpenFinanceUnavailableError,
)


async def test_consulta_perfil_open_finance_y_normaliza_montos():
    cliente_id = uuid.uuid4()
    llamadas = []

    def handler(request: httpx.Request) -> httpx.Response:
        llamadas.append(request)
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
        gateway = OpenFinanceHttpClient(client, "https://open-finance.test")
        perfil = await gateway.obtener_perfil_financiero(cliente_id)

    assert str(llamadas[0].url) == "https://open-finance.test/profile"
    assert llamadas[0].method == "POST"
    assert perfil.ingreso_mensual == Decimal("8500000")
    assert perfil.ahorros_liquidos == Decimal("25500000")
    assert perfil.dti_pct == Decimal("28")


@pytest.mark.parametrize(
    "response", [
        httpx.Response(503, json={"detail": "caído"}),
        httpx.Response(200, json={"ingreso_mensual": "inválido"}),
    ]
)
async def test_convierte_falla_o_respuesta_invalida_en_indisponibilidad(response):
    def handler(_request: httpx.Request) -> httpx.Response:
        return response

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        gateway = OpenFinanceHttpClient(client, "https://open-finance.test")

        with pytest.raises(OpenFinanceUnavailableError):
            await gateway.obtener_perfil_financiero(uuid.uuid4())
