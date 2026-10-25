import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.perfil_cliente_gateway import (
    ClienteNoEncontradoError,
    ConsentimientoNoOtorgadoError,
    PerfilNoDisponibleError,
)
from src.core.config import settings
from src.infrastructure.persistence.seed import sembrar_catalogo
from tests.fakes import FakePerfilGateway

BASE = f"{settings.API_PREFIX}/cotizaciones"


@pytest.fixture(autouse=True)
async def catalogo(db_session: AsyncSession):
    await sembrar_catalogo(db_session)


def _payload(**extra):
    return {
        "cliente_id": str(uuid.uuid4()),
        "producto_codigo": "VIDA_HIPOTECARIO",
        "parametros": {"valor_vivienda": 200000000},
        **extra,
    }


async def test_cotiza_vida_hipotecario(
    api_client: AsyncClient, fake_gateway: FakePerfilGateway
):
    payload = _payload()

    response = await api_client.post(BASE, json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["producto_codigo"] == "VIDA_HIPOTECARIO"
    assert data["moneda"] == "COP"
    assert float(data["prima_base"]) == 50000.0
    assert data["ajustes"] == []
    assert data["impuestos"][0]["concepto"] == "IVA"
    assert float(data["impuestos"][0]["valor"]) == 9500.0
    assert float(data["prima_total"]) == 59500.0
    assert data["degradada"] is False
    assert len(data["coberturas"]) == 2
    assert sum(float(c["prima"]) for c in data["coberturas"]) == pytest.approx(59500.0)
    assert fake_gateway.llamadas == [uuid.UUID(payload["cliente_id"])]


async def test_consulta_cotizacion_guardada(api_client: AsyncClient):
    creada = (await api_client.post(BASE, json=_payload())).json()

    response = await api_client.get(f"{BASE}/{creada['cotizacion_id']}")

    assert response.status_code == 200
    assert response.json()["prima_total"] == creada["prima_total"]
    assert response.json()["impuestos"] == creada["impuestos"]
    assert len(response.json()["coberturas"]) == 2


async def test_cotizacion_inexistente(api_client: AsyncClient):
    assert (await api_client.get(f"{BASE}/{uuid.uuid4()}")).status_code == 404


@pytest.mark.parametrize(
    ("error", "motivo"),
    [
        (PerfilNoDisponibleError(), "PERFIL_NO_DISPONIBLE"),
        (ConsentimientoNoOtorgadoError(), "PERFIL_SIN_CONSENTIMIENTO"),
    ],
)
async def test_degradacion_controlada_sin_perfil(
    api_client: AsyncClient, fake_gateway: FakePerfilGateway, error, motivo
):
    fake_gateway.error = error

    response = await api_client.post(BASE, json=_payload())

    assert response.status_code == 201
    data = response.json()
    assert data["degradada"] is True
    assert data["motivos_degradacion"] == [motivo]
    assert float(data["prima_total"]) == 59500.0


async def test_cliente_inexistente(
    api_client: AsyncClient, fake_gateway: FakePerfilGateway
):
    fake_gateway.error = ClienteNoEncontradoError()

    response = await api_client.post(BASE, json=_payload())

    assert response.status_code == 404


@pytest.mark.parametrize(
    "producto, parametro",
    [
        ("PROTECCION_PAGOS", "valor_cuota_mensual"),
        ("SEGURO_VIAJE", "valor_viaje"),
        ("PROTECCION_DISPOSITIVOS", "valor_dispositivo"),
        ("MICROSEGURO_VIDA", "suma_asegurada"),
        ("SEGURO_PARAMETRICO", "monto_compensacion"),
    ],
)
async def test_cotiza_otros_ramos_sin_consultar_perfil(
    api_client: AsyncClient, fake_gateway: FakePerfilGateway, producto, parametro
):
    response = await api_client.post(
        BASE,
        json=_payload(producto_codigo=producto, parametros={parametro: 1000000}),
    )

    assert response.status_code == 201
    assert float(response.json()["prima_total"]) > 0
    assert fake_gateway.llamadas == []


@pytest.mark.parametrize(
    "parametros",
    [{}, {"valor_vivienda": "abc"}, {"valor_vivienda": 0}, {"valor_vivienda": None}],
)
async def test_parametros_invalidos(api_client: AsyncClient, parametros):
    response = await api_client.post(BASE, json=_payload(parametros=parametros))

    assert response.status_code == 422
    assert "valor_vivienda" in response.json()["detail"][0]


async def test_ramo_inexistente(api_client: AsyncClient):
    response = await api_client.post(BASE, json=_payload(producto_codigo="NO_EXISTE"))

    assert response.status_code == 404


async def test_cuerpo_invalido(api_client: AsyncClient):
    response = await api_client.post(BASE, json={"cliente_id": "no-uuid"})

    assert response.status_code == 422
