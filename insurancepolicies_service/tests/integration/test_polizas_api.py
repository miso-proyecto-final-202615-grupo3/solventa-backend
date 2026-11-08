import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from src.domain.polizas.entities import Poliza, PolizaCobertura
from src.main import app
from src.presentation.dependencies import get_poliza_repository

CLIENTE_ID = uuid.uuid4()
OTRO_CLIENTE_ID = uuid.uuid4()
POLIZA_ID = uuid.uuid4()


def _poliza(cliente_id: uuid.UUID = CLIENTE_ID) -> Poliza:
    creada = datetime(2026, 1, 1, tzinfo=UTC)
    return Poliza(
        poliza_id=POLIZA_ID,
        cliente_id=cliente_id,
        cotizacion_id=uuid.uuid4(),
        producto_id=uuid.uuid4(),
        numero="POL-0001",
        estado="EMITIDA",
        vigencia_desde=creada,
        vigencia_hasta=creada + timedelta(days=365),
        emitida_en=creada,
        coberturas=[
            PolizaCobertura(
                poliza_id=POLIZA_ID,
                cobertura_id=uuid.uuid4(),
                limite_asegurado=Decimal("1000000.00"),
                deducible=Decimal("50000.00"),
                prima=Decimal("12000.50"),
            )
        ],
    )


class FakePolizaRepository:
    def __init__(self, polizas: list[Poliza]) -> None:
        self.polizas = polizas

    async def listar_por_cliente(self, cliente_id: uuid.UUID) -> list[Poliza]:
        return [poliza for poliza in self.polizas if poliza.cliente_id == cliente_id]

    async def obtener_por_id(self, poliza_id: uuid.UUID) -> Poliza | None:
        return next((p for p in self.polizas if p.poliza_id == poliza_id), None)


@pytest.fixture
def repository():
    repository = FakePolizaRepository([_poliza()])
    app.dependency_overrides[get_poliza_repository] = lambda: repository
    yield repository
    app.dependency_overrides.clear()


async def test_lista_solo_las_polizas_del_cliente(async_client, repository):
    response = await async_client.get(
        "/polizas/mis-polizas", headers={"X-Client-Id": str(CLIENTE_ID)}
    )

    assert response.status_code == 200
    assert response.json()[0]["numero"] == "POL-0001"
    assert response.json()[0]["prima_total"] == "12000.50"


async def test_cliente_no_puede_consultar_poliza_de_otro_cliente(async_client, repository):
    response = await async_client.get(
        f"/polizas/{POLIZA_ID}", headers={"X-Client-Id": str(OTRO_CLIENTE_ID)}
    )

    assert response.status_code == 403


async def test_cliente_consulta_el_detalle_de_su_poliza(async_client, repository):
    response = await async_client.get(
        f"/polizas/{POLIZA_ID}", headers={"X-Client-Id": str(CLIENTE_ID)}
    )

    assert response.status_code == 200
    assert response.json()["coberturas"][0]["deducible"] == "50000.00"
