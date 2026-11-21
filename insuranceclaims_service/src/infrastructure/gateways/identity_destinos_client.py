"""Destinos push del cliente en MS Identidad (HU4.2.2, §3.3). El token nunca viaja en la URL."""
from uuid import UUID

import httpx

from src.application.ports.destinos_push import DestinoPush, DestinosPush

PREFIJO = "/api/v1/identity-service/clientes"


class IdentityDestinosClient(DestinosPush):
    def __init__(self, base_url: str, timeout: float = 3.0, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout, transport=transport)

    async def listar(self, cliente_id: UUID, correlation_id: str) -> list[DestinoPush]:
        response = await self._client.get(
            f"{PREFIJO}/{cliente_id}/destinos-push", headers={"X-Correlation-Id": correlation_id}
        )
        response.raise_for_status()
        return [
            DestinoPush(installation_id=d["installation_id"], token=d["token"], plataforma=d["plataforma"])
            for d in response.json().get("destinos", [])
        ]

    async def eliminar(self, token: str, correlation_id: str) -> None:
        response = await self._client.post(
            f"{PREFIJO}/destinos-push/eliminacion", json={"token": token}, headers={"X-Correlation-Id": correlation_id}
        )
        response.raise_for_status()

    async def aclose(self) -> None:
        await self._client.aclose()
