from typing import Any
from uuid import UUID

import httpx

from src.core.config import settings
from src.infrastructure.gateways.backend_gateway import BackendGateway


class QuotingEngineServiceGateway(BackendGateway):
    def __init__(self, client: httpx.AsyncClient) -> None:
        super().__init__(client, settings.QUOTINGENGINE_SERVICE_URL, "/api/v1/quotingengine-service")

    async def productos(self, codigo: str, headers: dict[str, str]) -> httpx.Response:
        path = "/productos" + (f"/{codigo}" if codigo else "")
        return await self.request("GET", path, headers=headers)

    async def crear_cotizacion(
        self, payload: dict[str, Any], headers: dict[str, str]
    ) -> httpx.Response:
        return await self.request("POST", "/cotizaciones", json=payload, headers=headers)

    async def obtener_cotizacion(self, cotizacion_id: UUID) -> httpx.Response:
        return await self.request("GET", f"/cotizaciones/{cotizacion_id}")

    async def cotizacion(
        self, method: str, cotizacion_id: UUID, suffix: str, body: bytes | None,
        headers: dict[str, str],
    ) -> httpx.Response:
        return await self.request(
            method, f"/cotizaciones/{cotizacion_id}{suffix}", content=body, headers=headers
        )
