from typing import Any

import httpx

from src.core.config import settings


class InsurancePoliciesGatewayError(Exception):
    def __init__(self, status_code: int, detail: Any) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(str(detail))


class InsurancePoliciesServiceGateway:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.INSURANCEPOLICIES_SERVICE_URL,
            timeout=5.0,
            transport=transport,
        )

    async def listar_mis_polizas(self, client_id: str) -> list[dict[str, Any]]:
        return await self._request("GET", "/polizas/mis-polizas", client_id)

    async def obtener_poliza(self, poliza_id: str, client_id: str) -> dict[str, Any]:
        return await self._request(
            "GET", f"/polizas/{poliza_id}", client_id
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, client_id: str) -> Any:
        try:
            response = await self._client.request(
                method, path, headers={"X-Client-Id": client_id}
            )
        except httpx.HTTPError as exc:
            raise InsurancePoliciesGatewayError(
                503, "El servicio de pólizas no está disponible."
            ) from exc

        try:
            body = response.json()
        except ValueError:
            body = None

        if not response.is_success:
            detail = (
                body.get("detail", "El servicio de pólizas devolvió un error.")
                if isinstance(body, dict)
                else body or "El servicio de pólizas devolvió un error."
            )
            raise InsurancePoliciesGatewayError(response.status_code, detail)
        return body
