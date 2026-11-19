from uuid import UUID

import httpx

from src.core.config import settings
from src.infrastructure.gateways.backend_gateway import BackendGateway


class IdentityServiceGateway(BackendGateway):
    def __init__(self, client: httpx.AsyncClient) -> None:
        super().__init__(client, settings.IDENTITY_SERVICE_URL, "/api/v1/identity-service")

    async def validar_api_key(self, api_key: str) -> httpx.Response:
        return await self.request("POST", "/socios/validar-api-key", json={"api_key": api_key})

    async def validar_asociacion(self, socio_id: UUID, cliente_id: UUID) -> httpx.Response:
        return await self.request(
            "GET", f"/socios/{socio_id}/clientes/{cliente_id}/autorizacion"
        )

    async def registrar_prospecto(
        self, socio_id: UUID, body: bytes, headers: dict[str, str]
    ) -> httpx.Response:
        return await self.request(
            "POST", f"/socios/{socio_id}/prospectos", content=body, headers=headers
        )

    async def cliente(
        self, method: str, cliente_id: UUID, suffix: str, body: bytes | None,
        headers: dict[str, str],
    ) -> httpx.Response:
        return await self.request(
            method, f"/clientes/{cliente_id}{suffix}", content=body, headers=headers
        )
