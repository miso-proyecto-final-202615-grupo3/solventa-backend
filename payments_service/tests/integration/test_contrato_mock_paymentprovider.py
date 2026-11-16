"""Contrato entre payments_service y mock_paymentprovider: usa la aplicación real del mock."""
import importlib.util
from collections.abc import AsyncGenerator
from decimal import Decimal
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from pagos_fakes import CLIENTE_ID, COTIZACION_ID, CotizacionesFalsas, FirmasFalsas
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.proveedor_pago import DatosTarjeta, SolicitudCobro
from src.domain.pagos.entities import MetodoPago
from src.infrastructure.gateways.payment_provider_http_client import (
    ClienteProveedorPago,
    PayPalProveedor,
    TarjetaCreditoProveedor,
)
from src.infrastructure.persistence.models import EventoOutboxModel
from src.main import app
from src.presentation.dependencies import (
    get_cotizacion_gateway,
    get_db,
    get_firma_gateway,
    get_proveedores_pago,
)

MOCK_MAIN = Path(__file__).resolve().parents[3] / "mock_paymentprovider" / "src" / "main.py"
pytestmark = pytest.mark.skipif(not MOCK_MAIN.exists(), reason="mock_paymentprovider no disponible")


@pytest.fixture(scope="module")
def mock_app():
    # Se carga con otro nombre de módulo: ambos servicios usan el paquete `src`.
    spec = importlib.util.spec_from_file_location("mock_paymentprovider_main", MOCK_MAIN)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo.app


@pytest.fixture
async def cliente_mock(mock_app) -> AsyncGenerator[ClienteProveedorPago, None]:
    cliente = ClienteProveedorPago("http://mock", transport=ASGITransport(app=mock_app))
    yield cliente
    await cliente.aclose()


def _cobro(credencial: str, referencia: str = "pago-1") -> SolicitudCobro:
    return SolicitudCobro(
        referencia=referencia,
        monto=Decimal("1250000.51"),
        moneda="COP",
        credencial=credencial,
        correlation_id="corr-1",
    )


@pytest.mark.parametrize(
    ("correo", "aprobado", "codigo"),
    [
        ("cliente@example.com", True, None),
        ("declined@example.com", False, "INSTRUMENT_DECLINED"),
        ("nofunds@example.com", False, "INSUFFICIENT_FUNDS"),
    ],
)
async def test_paypal_contra_el_mock(cliente_mock, correo, aprobado, codigo):
    resultado = await PayPalProveedor(cliente_mock).cobrar(_cobro(correo))

    assert (resultado.aprobado, resultado.codigo_rechazo) == (aprobado, codigo)
    assert resultado.referencia.startswith("PAYPAL_")


async def test_la_misma_referencia_devuelve_la_misma_referencia_del_proveedor(cliente_mock):
    proveedor = PayPalProveedor(cliente_mock)

    primero = await proveedor.cobrar(_cobro("cliente@example.com", "pago-1"))
    repetido = await proveedor.cobrar(_cobro("cliente@example.com", "pago-1"))
    otro = await proveedor.cobrar(_cobro("cliente@example.com", "pago-2"))

    assert primero.referencia == repetido.referencia != otro.referencia


@pytest.mark.parametrize(
    ("numero", "aprobado", "codigo"),
    [
        ("4242424242424242", True, None),
        ("4000000000000002", False, "card_declined"),
        ("4000000000009995", False, "insufficient_funds"),
        ("4000000000000069", False, "expired_card"),
    ],
)
async def test_tarjeta_contra_el_mock_con_token_del_servicio(cliente_mock, numero, aprobado, codigo):
    proveedor = TarjetaCreditoProveedor(cliente_mock)
    token = await proveedor.tokenizar(DatosTarjeta(numero, 12, 2099, "123"), "corr-1")

    resultado = await proveedor.cobrar(_cobro(token))

    assert (resultado.aprobado, resultado.codigo_rechazo) == (aprobado, codigo)
    assert (resultado.tarjeta_ultimos4, resultado.tarjeta_marca) == (numero[-4:], "VISA")


@pytest.fixture
async def client(db_session: AsyncSession, cliente_mock) -> AsyncGenerator[AsyncClient, None]:
    async def _db():
        yield db_session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_cotizacion_gateway] = lambda: CotizacionesFalsas()
    app.dependency_overrides[get_firma_gateway] = lambda: FirmasFalsas()
    app.dependency_overrides[get_proveedores_pago] = lambda: {
        MetodoPago.PAYPAL: PayPalProveedor(cliente_mock),
        MetodoPago.TARJETA_CREDITO: TarjetaCreditoProveedor(cliente_mock),
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


def _pagar(client: AsyncClient, cuerpo: dict, clave: str):
    return client.post(
        "/api/v1/payments-service/pagos", json=cuerpo, headers={"Idempotency-Key": clave}
    )


_BASE = {"cotizacion_id": str(COTIZACION_ID), "cliente_id": str(CLIENTE_ID)}


async def test_flujo_completo_rechazo_con_paypal_y_luego_pago_con_tarjeta(
    client, db_session: AsyncSession
):
    rechazado = await _pagar(client, {**_BASE, "paypal_email": "nofunds@example.com"}, "k1")
    assert rechazado.status_code == 201
    assert (rechazado.json()["estado"], rechazado.json()["codigo_rechazo"]) == (
        "RECHAZADO",
        "INSUFFICIENT_FUNDS",
    )
    assert (await db_session.execute(select(EventoOutboxModel))).first() is None

    aprobado = await _pagar(
        client,
        {
            **_BASE, "metodo_pago": "TARJETA_CREDITO",
            "numero_tarjeta": "4242424242424242", "mes_expiracion": 12,
            "anio_expiracion": 2099, "cvv": "123",
        },
        "k2",
    )
    assert aprobado.status_code == 201
    assert aprobado.json()["estado"] == "APROBADO"
    assert aprobado.json()["tarjeta_ultimos4"] == "4242"
    (evento,) = (await db_session.execute(select(EventoOutboxModel))).scalars().all()
    assert evento.payload["datos"]["pago_id"] == aprobado.json()["pago_id"]
    assert evento.payload["datos"]["metodo_pago"] == "TARJETA_CREDITO"
