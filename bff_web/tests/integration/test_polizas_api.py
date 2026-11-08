import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from src.infrastructure.gateways.insurancepolicies_service_gateway import (
    InsurancePoliciesGatewayError,
)
from src.main import app
from src.presentation.dependencies import get_insurancepolicies_service_gateway

CLIENTE_ID = uuid.uuid4()
POLIZA_ID = uuid.uuid4()
POLIZA = {"poliza_id": str(POLIZA_ID), "numero": "POL-0001"}


class FakeInsurancePoliciesGateway:
    def __init__(self):
        self.calls: list[tuple] = []
        self.error: tuple[int, str] | None = None

    def _check_error(self) -> None:
        if self.error:
            raise InsurancePoliciesGatewayError(*self.error)

    async def listar_mis_polizas(self, client_id: str):
        self.calls.append(("listar_mis_polizas", client_id))
        self._check_error()
        return [POLIZA]

    async def obtener_poliza(self, poliza_id: str, client_id: str):
        self.calls.append(("obtener_poliza", poliza_id, client_id))
        self._check_error()
        return POLIZA

    async def aclose(self):
        pass


@pytest.fixture
async def bff_client():
    gateway = FakeInsurancePoliciesGateway()
    app.dependency_overrides[get_insurancepolicies_service_gateway] = lambda: gateway
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, gateway
    app.dependency_overrides.clear()


async def test_expone_listado_y_detalle_de_polizas(bff_client):
    client, gateway = bff_client
    listado = await client.get(
        "/api/v1/bff-web/polizas/mis-polizas",
        headers={"X-Client-Id": str(CLIENTE_ID)},
    )
    detalle = await client.get(
        f"/api/v1/bff-web/polizas/{POLIZA_ID}",
        headers={"X-Client-Id": str(CLIENTE_ID)},
    )

    assert listado.status_code == 200
    assert detalle.status_code == 200
    assert gateway.calls == [
        ("listar_mis_polizas", str(CLIENTE_ID)),
        ("obtener_poliza", str(POLIZA_ID), str(CLIENTE_ID)),
    ]


async def test_propagacion_de_error_del_ms_de_polizas(bff_client):
    client, gateway = bff_client
    gateway.error = (403, "No puedes consultar esta póliza.")

    response = await client.get(
        f"/api/v1/bff-web/polizas/{POLIZA_ID}",
        headers={"X-Client-Id": str(CLIENTE_ID)},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "No puedes consultar esta póliza."
