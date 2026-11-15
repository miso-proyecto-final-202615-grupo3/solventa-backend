import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from src.domain.polizas.entities import Poliza, PolizaCobertura
from src.domain.eventos.trazabilidad import EventoTrazabilidadPoliza
from src.main import app
from src.presentation.dependencies import get_auditoria_poliza_repository, get_poliza_repository

CLIENTE_ID = uuid.uuid4()
OTRO_CLIENTE_ID = uuid.uuid4()
POLIZA_ID = uuid.uuid4()
PREFIJO = "/api/v1/insurancepolicies-service"


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
        ramo="VIAJE",
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


class FakeAuditoriaRepository:
    async def listar_por_cotizacion(self, cotizacion_id: uuid.UUID):
        return [
            EventoTrazabilidadPoliza(
                cotizacion_id=cotizacion_id,
                cliente_id=CLIENTE_ID,
                tipo="POLIZA_EMITIDA",
                ocurrido_en=datetime(2026, 1, 1, tzinfo=UTC),
                origen="insurancepolicies_service",
                resultado="EMITIDA",
                referencia_id=str(POLIZA_ID),
            )
        ]


@pytest.fixture
def repository():
    repository = FakePolizaRepository([_poliza()])
    app.dependency_overrides[get_poliza_repository] = lambda: repository
    app.dependency_overrides[get_auditoria_poliza_repository] = FakeAuditoriaRepository
    yield repository
    app.dependency_overrides.clear()


async def test_lista_solo_las_polizas_del_cliente(async_client, repository):
    response = await async_client.get(
        f"{PREFIJO}/polizas/mis-polizas", headers={"X-Client-Id": str(CLIENTE_ID)}
    )

    assert response.status_code == 200
    assert response.json()[0]["numero"] == "POL-0001"
    assert response.json()[0]["prima_total"] == "12000.50"
    assert response.json()[0]["ramo"] == "VIAJE"
    assert response.json()[0]["historial"][0]["tipo"] == "POLIZA_EMITIDA"


async def test_cliente_no_puede_consultar_poliza_de_otro_cliente(async_client, repository):
    response = await async_client.get(
        f"{PREFIJO}/polizas/{POLIZA_ID}", headers={"X-Client-Id": str(OTRO_CLIENTE_ID)}
    )

    assert response.status_code == 403


async def test_cliente_consulta_el_detalle_de_su_poliza(async_client, repository):
    response = await async_client.get(
        f"{PREFIJO}/polizas/{POLIZA_ID}", headers={"X-Client-Id": str(CLIENTE_ID)}
    )

    assert response.status_code == 200
    assert response.json()["coberturas"][0]["deducible"] == "50000.00"
    assert response.json()["historial"][0]["resultado"] == "EMITIDA"


async def test_consulta_requiere_cliente_y_poliza_existente(async_client, repository):
    sin_cliente = await async_client.get(f"{PREFIJO}/polizas/mis-polizas")
    inexistente = await async_client.get(
        f"{PREFIJO}/polizas/{uuid.uuid4()}", headers={"X-Client-Id": str(CLIENTE_ID)}
    )

    assert sin_cliente.status_code == 422
    assert inexistente.status_code == 404


async def test_openapi_y_rutas_solo_exponen_el_prefijo_del_servicio(async_client):
    paths = (await async_client.get("/openapi.json")).json()["paths"]
    assert "get" in paths[f"{PREFIJO}/polizas/mis-polizas"]
    assert "get" in paths[f"{PREFIJO}/polizas/{{poliza_id}}"]
    assert "/polizas/mis-polizas" not in paths
    assert "/polizas/{poliza_id}" not in paths

    for path in ("/polizas/mis-polizas", f"/polizas/{POLIZA_ID}"):
        response = await async_client.get(path, headers={"X-Client-Id": str(CLIENTE_ID)})
        assert response.status_code == 404
