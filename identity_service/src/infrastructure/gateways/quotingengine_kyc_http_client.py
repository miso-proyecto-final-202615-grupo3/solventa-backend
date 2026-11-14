import uuid

import httpx

from src.application.ports.cotizacion_kyc import (
    CotizacionKycGateway,
    CotizacionNoDisponibleError,
    CotizacionNoEncontradaError,
    CotizacionNoPerteneceAlClienteError,
)
from src.core.config import settings


class QuotingEngineKycHttpClient(CotizacionKycGateway):
    def __init__(
        self,
        base_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url or settings.QUOTINGENGINE_SERVICE_URL,
            timeout=settings.KYC_QUOTINGENGINE_TIMEOUT_SECONDS,
            transport=transport,
        )

    async def validar_cliente(
        self, cotizacion_id: uuid.UUID, cliente_id: uuid.UUID, correlation_id: str
    ) -> None:
        try:
            response = await self._client.get(
                f"/api/v1/quotingengine-service/cotizaciones/{cotizacion_id}",
                headers={"X-Correlation-Id": correlation_id},
            )
        except httpx.HTTPError as exc:
            raise CotizacionNoDisponibleError("El motor de cotización no está disponible.") from exc
        if response.status_code == 404:
            raise CotizacionNoEncontradaError("Cotización no encontrada.")
        if not response.is_success:
            raise CotizacionNoDisponibleError("El motor de cotización devolvió un error.")
        try:
            body = response.json()
            propietario = uuid.UUID(str(body["cliente_id"]))
        except (ValueError, TypeError, KeyError) as exc:
            raise CotizacionNoDisponibleError("El motor de cotización devolvió una respuesta inválida.") from exc
        if propietario != cliente_id:
            raise CotizacionNoPerteneceAlClienteError("La cotización no pertenece al cliente.")

    async def aclose(self) -> None:
        await self._client.aclose()
