import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.perfil_cliente_gateway import (
    ClienteNoEncontradoError,
    ConsentimientoNoOtorgadoError,
    PerfilNoDisponibleError,
)
from src.application.ports.open_data_gateway import OpenDataNoDisponibleError
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
        "parametros": {
            "saldo_credito": 200000000,
            "ubicacion": {
                "municipio": "Bogotá D.C.",
                "zona": "URBANA",
                "estrato": 4,
            },
        },
        **extra,
    }


def _verificar_vigencia(particulares, cotizacion, anos):
    assert set(particulares) == {"prima_total", "moneda", "vigencia_propuesta", "coberturas"}
    vigencia = particulares["vigencia_propuesta"]
    assert set(vigencia) == {"desde", "hasta"}
    creada_en = datetime.fromisoformat(cotizacion["creada_en"])
    if creada_en.tzinfo is None:
        creada_en = creada_en.replace(tzinfo=timezone.utc)
    assert datetime.fromisoformat(vigencia["desde"]) == creada_en
    dia = 28 if creada_en.month == 2 and creada_en.day == 29 else creada_en.day
    assert datetime.fromisoformat(vigencia["hasta"]) == creada_en.replace(year=creada_en.year + anos, day=dia)


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
    assert float(data["prima_neta"]) == 40375.0
    assert [(a["concepto"], a["tipo"], float(a["valor"])) for a in data["ajustes"]] == [
        ("OPEN_FINANCE", "DEDUCCION", 7500.0),
        ("OPEN_DATA", "DEDUCCION", 2125.0),
    ]
    assert data["impuestos"][0]["concepto"] == "IVA"
    assert float(data["impuestos"][0]["valor"]) == 7671.25
    assert float(data["prima_total"]) == 48046.25
    assert data["degradada"] is False
    assert len(data["coberturas"]) == 2
    assert sum(float(c["prima"]) for c in data["coberturas"]) == pytest.approx(48046.25)
    assert fake_gateway.llamadas == [uuid.UUID(payload["cliente_id"])]
    condiciones = await api_client.get(
        f"{BASE}/{data['cotizacion_id']}/condiciones",
    )
    assert condiciones.status_code == 200
    particulares = condiciones.json()["condiciones_particulares"]
    _verificar_vigencia(particulares, data, 10)
    assert len(particulares["coberturas"]) == 2
    assert all(set(c) == {"prima", "limite_asegurado", "deducible"} for c in particulares["coberturas"])


async def test_open_data_usa_cache_territorial_si_proveedor_no_disponible(
    api_client: AsyncClient,
    fake_open_data_gateway,
):
    primera = await api_client.post(BASE, json=_payload())
    assert primera.status_code == 201
    fake_open_data_gateway.error = OpenDataNoDisponibleError()

    respuesta = await api_client.post(BASE, json=_payload())

    assert respuesta.status_code == 201
    data = respuesta.json()
    assert float(data["prima_total"]) == 48046.25
    assert data["degradada"] is True
    assert data["motivos_degradacion"] == ["OPEN_DATA_CACHE"]


async def test_open_data_sin_cache_aplica_factor_neutral(
    api_client: AsyncClient,
    fake_open_data_gateway,
):
    fake_open_data_gateway.error = OpenDataNoDisponibleError()

    respuesta = await api_client.post(BASE, json=_payload())

    assert respuesta.status_code == 201
    data = respuesta.json()
    assert float(data["prima_total"]) == 50575.0
    assert data["degradada"] is True
    assert data["motivos_degradacion"] == ["OPEN_DATA_NO_DISPONIBLE"]


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
    assert float(data["prima_total"]) == 56525.0


async def test_consentimiento_inactivo_rechaza_cotizacion(
    api_client: AsyncClient, fake_gateway: FakePerfilGateway
):
    fake_gateway.error = ConsentimientoNoOtorgadoError()

    response = await api_client.post(BASE, json=_payload())

    assert response.status_code == 403


async def test_cliente_inexistente(
    api_client: AsyncClient, fake_gateway: FakePerfilGateway
):
    fake_gateway.error = ClienteNoEncontradoError()

    response = await api_client.post(BASE, json=_payload())

    assert response.status_code == 404


@pytest.mark.parametrize(
    "producto, parametro, anos",
    [
        ("PROTECCION_PAGOS", "valor_cuota_mensual", 10),
        ("SEGURO_VIAJE", "valor_viaje", 1),
        ("PROTECCION_DISPOSITIVOS", "valor_dispositivo", 1),
        ("MICROSEGURO_VIDA", "suma_asegurada", 10),
        ("SEGURO_PARAMETRICO", "monto_compensacion", 1),
    ],
)
async def test_cotiza_otros_ramos_sin_consultar_perfil(
    api_client: AsyncClient, fake_gateway: FakePerfilGateway, producto, parametro, anos
):
    response = await api_client.post(
        BASE,
        json=_payload(producto_codigo=producto, parametros={parametro: 1000000}),
    )

    assert response.status_code == 201
    assert float(response.json()["prima_total"]) > 0
    assert fake_gateway.llamadas == []
    data = response.json()
    condiciones = await api_client.get(
        f"{BASE}/{data['cotizacion_id']}/condiciones",
    )
    assert condiciones.status_code == 200
    assert condiciones.json()["condiciones_generales"]
    particulares = condiciones.json()["condiciones_particulares"]
    _verificar_vigencia(particulares, data, anos)
    assert particulares["prima_total"] == data["prima_total"]
    assert len(particulares["coberturas"]) == len(data["coberturas"])
    assert all(set(c) == {"prima", "limite_asegurado", "deducible"} for c in particulares["coberturas"])


@pytest.mark.parametrize(
    "parametros",
    [
        {},
        {"saldo_credito": "abc", "ubicacion": _payload()["parametros"]["ubicacion"]},
        {"saldo_credito": 0, "ubicacion": _payload()["parametros"]["ubicacion"]},
        {"saldo_credito": None, "ubicacion": _payload()["parametros"]["ubicacion"]},
    ],
)
async def test_parametros_invalidos(api_client: AsyncClient, parametros):
    response = await api_client.post(BASE, json=_payload(parametros=parametros))

    assert response.status_code == 422


async def test_rechaza_ubicacion_con_tipo_invalido(api_client: AsyncClient):
    payload = _payload()
    payload["parametros"]["ubicacion"]["zona"] = []

    response = await api_client.post(BASE, json=payload)

    assert response.status_code == 422


async def test_ramo_inexistente(api_client: AsyncClient):
    response = await api_client.post(BASE, json=_payload(producto_codigo="NO_EXISTE"))

    assert response.status_code == 404


async def test_cuerpo_invalido(api_client: AsyncClient):
    response = await api_client.post(BASE, json={"cliente_id": "no-uuid"})

    assert response.status_code == 422
