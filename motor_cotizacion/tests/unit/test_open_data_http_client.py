from decimal import Decimal

import httpx
import pytest

from src.application.ports.perfilamiento import OpenDataNoDisponibleError
from src.domain.open_data import CategoriaOpenData
from src.infrastructure.gateways.open_data_http_client import OpenDataHttpClient


async def test_consulta_fuente_open_data_y_normaliza_categoria():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "categoria": "BAJO_RIESGO",
                "id_territorial": 0.95,
                "ir_publico": 1.0,
            },
        )

    location = {"municipio": "Bogota", "zona": "URBANA", "estrato": 4}
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        gateway = OpenDataHttpClient(client, "https://open-data.test")
        profile = await gateway.obtener_riesgo_territorial(location)

    assert str(calls[0].url) == "https://open-data.test/risk"
    assert calls[0].method == "POST"
    assert profile.categoria == CategoriaOpenData.BAJO_RIESGO
    assert profile.id_territorial == Decimal("0.95")
    assert profile.ir_publico == Decimal("1.0")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503, json={"detail": "down"}),
        httpx.Response(200, json={"categoria": "DESCONOCIDA"}),
    ],
)
async def test_convierte_falla_o_categoria_desconocida_en_indisponibilidad(
    response,
):
    def handler(_request: httpx.Request) -> httpx.Response:
        return response

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        gateway = OpenDataHttpClient(client, "https://open-data.test")

        with pytest.raises(OpenDataNoDisponibleError):
            await gateway.obtener_riesgo_territorial(
                {"municipio": "Bogota", "zona": "URBANA", "estrato": 4}
            )
