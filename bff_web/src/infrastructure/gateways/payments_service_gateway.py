from typing import Any
from uuid import UUID

import httpx

from src.core.config import settings


class PaymentsGatewayError(Exception):
    def __init__(self, status_code: int, detail: Any) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(str(detail))


class PaymentsServiceGateway:
    """Cliente HTTP hacia el servicio de pagos."""

    def __init__(
        self,
        base_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url or settings.PAYMENTS_SERVICE_URL,
            timeout=30.0,
            transport=transport,
        )

    async def obtener_resumen_pago(
        self, cotizacion_id: UUID, headers: dict[str, str]
    ) -> tuple[int, dict[str, Any]]:
        return await self._request("GET", f"/cotizaciones/{cotizacion_id}/resumen-pago", headers)

    async def procesar_pago(
        self, payload: bytes, headers: dict[str, str]
    ) -> tuple[int, dict[str, Any]]:
        return await self._request("POST", "/pagos", headers, payload)

    async def obtener_pago(
        self, pago_id: UUID, headers: dict[str, str]
    ) -> tuple[int, dict[str, Any]]:
        return await self._request("GET", f"/pagos/{pago_id}", headers)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        payload: bytes | None = None,
    ) -> tuple[int, dict[str, Any]]:
        try:
            response = await self._client.request(
                method,
                f"/api/v1/payments-service{path}",
                headers=headers,
                content=payload,
            )
        except httpx.HTTPError as exc:
            raise PaymentsGatewayError(
                503,
                "El servicio de pagos no está disponible. Si inició un pago, "
                "reintente con la misma Idempotency-Key.",
            ) from exc

        try:
            body = response.json()
        except ValueError as exc:
            if response.is_success:
                raise PaymentsGatewayError(
                    502, "El servicio de pagos devolvió una respuesta inválida."
                ) from exc
            body = None

        if not response.is_success:
            detail = (
                body.get("detail", "El servicio de pagos devolvió un error.")
                if isinstance(body, dict)
                else "El servicio de pagos devolvió un error."
            )
            raise PaymentsGatewayError(response.status_code, detail)
        if not isinstance(body, dict):
            raise PaymentsGatewayError(
                502, "El servicio de pagos devolvió una respuesta inválida."
            )
        return response.status_code, body
