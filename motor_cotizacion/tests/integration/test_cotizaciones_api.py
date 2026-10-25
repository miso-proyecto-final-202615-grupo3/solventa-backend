from datetime import UTC, datetime, timedelta
from decimal import Decimal
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from src.application.ports.perfilamiento import (
    ClienteCotizacionNoEncontradoError,
    ConsentimientoNoActivoError,
    PerfilamientoNoDisponibleError,
)
from src.application.use_cases.generar_cotizacion_use_case import (
    CotizacionGenerada,
    FuentePerfil,
)
from src.domain.open_data import CategoriaOpenData
from src.domain.pricing import CategoriaOpenFinance, ResultadoPricing
from src.main import app
from src.presentation.dependencies import get_generar_cotizacion_use_case


CLIENTE_ID = uuid.uuid4()
PAYLOAD = {
    "cliente_id": str(CLIENTE_ID),
    "ramo": "VIDA_HIPOTECARIO",
    "consentimiento_version": "1.0",
    "parametros": {
        "saldo_credito": 200000000,
        "ubicacion": {
            "municipio": "Bogota",
            "zona": "URBANA",
            "estrato": 4,
        },
    },
}


class FakeCotizarUseCase:
    def __init__(self):
        self.error: Exception | None = None
        self.command = None

    async def ejecutar(self, command):
        self.command = command
        if self.error:
            raise self.error
        return CotizacionGenerada(
            cotizacion_id=uuid.uuid4(),
            pricing=ResultadoPricing(
                categoria_open_finance=CategoriaOpenFinance.A,
                factor_open_finance=Decimal("0.85"),
                factor_open_data=Decimal("0.95"),
                prima_base=Decimal("50000.00"),
                ajuste_open_finance=Decimal("-7500.00"),
                ajuste_open_data=Decimal("-2125.00"),
                prima_neta=Decimal("40375.00"),
                impuestos=Decimal("7671.25"),
                prima_total=Decimal("48046.25"),
            ),
            categoria_open_data=CategoriaOpenData.BAJO_RIESGO,
            fuente_perfil=FuentePerfil.PROVEEDORES,
            open_finance_personalizado=True,
            vigencia_hasta=datetime.now(UTC) + timedelta(days=1),
        )


@pytest.fixture
async def motor_client():
    use_case = FakeCotizarUseCase()
    app.dependency_overrides[get_generar_cotizacion_use_case] = lambda: use_case
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client, use_case
    app.dependency_overrides.clear()


async def test_cotizar_devuelve_prima_y_desglose_sin_datos_financieros(
    motor_client,
):
    client, use_case = motor_client

    response = await client.post(
        "/api/v1/motor-cotizacion/cotizar", json=PAYLOAD
    )

    assert response.status_code == 200
    body = response.json()
    assert body["prima_mensual"] == 48046.25
    assert body["desglose"]["prima_base"] == 50000.0
    assert body["desglose"]["ajustes"] == -9625.0
    assert body["desglose"]["impuestos"] == 7671.25
    assert body["fuente_perfil"] == "PROVEEDORES"
    assert "ingreso_mensual" not in body
    assert use_case.command.cliente_id == CLIENTE_ID
    assert use_case.command.saldo_credito == Decimal("200000000")


@pytest.mark.parametrize(
    ("error", "status", "detail"),
    [
        (
            ConsentimientoNoActivoError(),
            403,
            "CONSENTIMIENTO_NO_ACTIVO",
        ),
        (
            ClienteCotizacionNoEncontradoError(),
            404,
            "CLIENTE_O_RAMO_NO_ENCONTRADO",
        ),
        (
            PerfilamientoNoDisponibleError(),
            503,
            "PERFILAMIENTO_NO_DISPONIBLE",
        ),
    ],
)
async def test_cotizar_mapea_errores_del_perfilamiento(
    motor_client, error, status, detail
):
    client, use_case = motor_client
    use_case.error = error

    response = await client.post(
        "/api/v1/motor-cotizacion/cotizar", json=PAYLOAD
    )

    assert response.status_code == status
    assert response.json()["detail"] == detail


async def test_cotizar_rechaza_saldo_no_positivo(motor_client):
    client, _ = motor_client

    response = await client.post(
        "/api/v1/motor-cotizacion/cotizar",
        json={
            **PAYLOAD,
            "parametros": {
                **PAYLOAD["parametros"],
                "saldo_credito": 0,
            },
        },
    )

    assert response.status_code == 422
