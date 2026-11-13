from datetime import timedelta

from src.application.use_cases.consultar_pago_use_case import (
    ConsultarPagoUseCase,
    ConsultarResumenPagoUseCase,
)
from src.core.config import settings
from src.domain.pagos.entities import MetodoPago
from src.infrastructure.gateways.insurancepolicies_http_client import InsurancePoliciesHttpClient
from src.infrastructure.gateways.payment_provider_http_client import (
    PayPalProveedor,
    TarjetaCreditoProveedor,
)
from src.infrastructure.gateways.quotingengine_http_client import QuotingEngineHttpClient
from src.presentation import dependencies as deps


async def test_gateways_y_proveedores_se_crean_y_cierran_por_request():
    gateways = deps.get_cotizacion_gateway(), deps.get_firma_gateway()
    clases = (QuotingEngineHttpClient, InsurancePoliciesHttpClient)
    for generador, clase in zip(gateways, clases):
        gateway = await anext(generador)
        assert isinstance(gateway, clase) and not gateway._client.is_closed
        await generador.aclose()
        assert gateway._client.is_closed

    generador = deps.get_proveedores_pago()
    proveedores = await anext(generador)
    assert isinstance(proveedores[MetodoPago.PAYPAL], PayPalProveedor)
    assert isinstance(proveedores[MetodoPago.TARJETA_CREDITO], TarjetaCreditoProveedor)
    cliente = proveedores[MetodoPago.PAYPAL]._cliente
    await generador.aclose()
    assert cliente._client.is_closed


async def test_arma_los_casos_de_uso_con_la_configuracion(db_session):
    caso = deps.get_procesar_pago_prima_use_case(db_session, "cotizaciones", "firmas", {})

    assert caso.cotizaciones == "cotizaciones" and caso.firmas == "firmas"
    assert caso.proveedor_nombre == settings.PAYMENT_PROVIDER_NAME
    assert caso.requiere_firma is settings.REQUIRE_FIRMA_DIGITAL
    assert caso.pendiente_ttl == timedelta(seconds=settings.PAGO_PENDIENTE_TTL_SECONDS)
    assert isinstance(deps.get_consultar_resumen_pago_use_case("x"), ConsultarResumenPagoUseCase)
    assert isinstance(deps.get_consultar_pago_use_case(db_session), ConsultarPagoUseCase)
