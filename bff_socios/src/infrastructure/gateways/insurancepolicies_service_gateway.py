from uuid import UUID

import httpx

from src.core.config import settings
from src.infrastructure.gateways.backend_gateway import BackendGateway


class InsurancePoliciesServiceGateway(BackendGateway):
    def __init__(self, client: httpx.AsyncClient) -> None:
        super().__init__(client, settings.INSURANCEPOLICIES_SERVICE_URL, "/api/v1/insurancepolicies-service")

    async def cotizacion(
        self, method: str, cotizacion_id: UUID, suffix: str, body: bytes | None,
        headers: dict[str, str],
    ) -> httpx.Response:
        return await self.request(
            method, f"/cotizaciones/{cotizacion_id}{suffix}", content=body, headers=headers
        )

    async def polizas(self, suffix: str, headers: dict[str, str]) -> httpx.Response:
        return await self.request("GET", f"/polizas{suffix}", headers=headers)
