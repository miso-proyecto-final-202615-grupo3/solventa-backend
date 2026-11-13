import re

import httpx

from src.application.ports.proveedor_pago import (
    DatosTarjeta,
    ProveedorPago,
    ProveedorPagoError,
    ProveedorTarjeta,
    ResultadoCobro,
    SolicitudCobro,
    SolicitudInvalidaError,
)
from src.core.config import settings


class ClienteProveedorPago:
    """Cliente HTTPS hacia la pasarela de pagos (o su mock); una instancia por request."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url or settings.PAYMENT_PROVIDER_URL,
            timeout=timeout or settings.PAYMENT_PROVIDER_TIMEOUT_SECONDS,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def crear(self, ruta: str, cuerpo: dict, solicitud: SolicitudCobro) -> dict:
        resultado = await self._post(
            ruta,
            cuerpo,
            {
                "Idempotency-Key": solicitud.referencia,
                "X-Correlation-Id": solicitud.correlation_id,
            },
        )
        if not resultado.get("id"):
            raise ProveedorPagoError("RESPUESTA_INVALIDA")
        return resultado

    async def tokenizar(self, tarjeta: DatosTarjeta, correlation_id: str) -> str:
        resultado = await self._post(
            "/credit-card/tokens",
            {
                "number": tarjeta.numero_tarjeta,
                "exp_month": tarjeta.mes_expiracion,
                "exp_year": tarjeta.anio_expiracion,
                "cvv": tarjeta.cvv,
            },
            {"X-Correlation-Id": correlation_id},
        )
        token = resultado.get("token")
        if not isinstance(token, str) or not re.fullmatch(r"tok_[A-Za-z0-9_]{1,96}", token):
            raise ProveedorPagoError("RESPUESTA_INVALIDA")
        return token

    async def _post(self, ruta: str, cuerpo: dict, headers: dict[str, str]) -> dict:
        try:
            response = await self._client.post(
                ruta,
                json=cuerpo,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise ProveedorPagoError(
                "PROVEEDOR_NO_DISPONIBLE", f"{type(exc).__name__} al contactar la pasarela."
            ) from exc
        if 400 <= response.status_code < 500:
            raise SolicitudInvalidaError(f"PROVEEDOR_HTTP_{response.status_code}")
        if not response.is_success:
            raise ProveedorPagoError(f"PROVEEDOR_HTTP_{response.status_code}")
        try:
            resultado = response.json()
        except ValueError as exc:
            raise ProveedorPagoError("RESPUESTA_INVALIDA") from exc
        if not isinstance(resultado, dict):
            raise ProveedorPagoError("RESPUESTA_INVALIDA")
        return resultado


class PayPalProveedor(ProveedorPago):
    def __init__(self, cliente: ClienteProveedorPago) -> None:
        self._cliente = cliente

    async def cobrar(self, solicitud: SolicitudCobro) -> ResultadoCobro:
        resultado = await self._cliente.crear(
            "/paypal/payments",
            {
                "payer_email": solicitud.credencial,
                "amount": str(solicitud.monto),
                "currency": solicitud.moneda,
                "reference": solicitud.referencia,
            },
            solicitud,
        )
        estado = resultado.get("status")
        if estado not in ("COMPLETED", "DECLINED"):
            raise ProveedorPagoError("RESPUESTA_INVALIDA", f"estado {estado!r}")
        return ResultadoCobro(
            aprobado=estado == "COMPLETED",
            referencia=str(resultado["id"]),
            codigo_rechazo=resultado.get("failure_code"),
        )


class TarjetaCreditoProveedor(ProveedorTarjeta):
    def __init__(self, cliente: ClienteProveedorPago) -> None:
        self._cliente = cliente

    async def tokenizar(self, tarjeta: DatosTarjeta, correlation_id: str) -> str:
        return await self._cliente.tokenizar(tarjeta, correlation_id)

    async def cobrar(self, solicitud: SolicitudCobro) -> ResultadoCobro:
        resultado = await self._cliente.crear(
            "/credit-card/charges",
            {
                "token": solicitud.credencial,
                "amount": str(solicitud.monto),
                "currency": solicitud.moneda,
                "reference": solicitud.referencia,
            },
            solicitud,
        )
        estado = resultado.get("status")
        if estado not in ("succeeded", "declined"):
            raise ProveedorPagoError("RESPUESTA_INVALIDA", f"estado {estado!r}")
        return ResultadoCobro(
            aprobado=estado == "succeeded",
            referencia=str(resultado["id"]),
            codigo_rechazo=resultado.get("failure_code"),
            tarjeta_ultimos4=resultado.get("last4"),
            tarjeta_marca=resultado.get("brand"),
        )
