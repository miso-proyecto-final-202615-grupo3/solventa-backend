from uuid import UUID

import httpx

from src.core.config import settings
from src.infrastructure.gateways.backend_gateway import BackendGateway


class PaymentsServiceGateway(BackendGateway):
    def __init__(self, client: httpx.AsyncClient) -> None:
        super().__init__(client, settings.PAYMENTS_SERVICE_URL, "/api/v1/payments-service")

    async def resumen_pago(self, cotizacion_id: UUID, headers: dict[str, str]) -> httpx.Response:
        return await self.request(
            "GET", f"/cotizaciones/{cotizacion_id}/resumen-pago", headers=headers
        )

    async def crear_pago(self, body: bytes, headers: dict[str, str]) -> httpx.Response:
        return await self.request("POST", "/pagos", content=body, headers=headers)

    async def obtener_pago(self, pago_id: UUID, headers: dict[str, str]) -> httpx.Response:
        return await self.request("GET", f"/pagos/{pago_id}", headers=headers)
