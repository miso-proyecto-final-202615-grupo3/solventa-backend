from typing import Any
from uuid import UUID

import httpx

from src.core.config import settings


class InsurancePoliciesGatewayError(Exception):
    def __init__(self, status_code: int, detail: Any) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(str(detail))


class InsurancePoliciesServiceGateway:
    """Cliente HTTP hacia el servicio de pólizas."""

    def __init__(
        self,
        base_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url or settings.INSURANCEPOLICIES_SERVICE_URL,
            timeout=30.0,
            transport=transport,
        )

    async def capturar_firma(
        self,
        cotizacion_id: UUID,
        payload: bytes,
        headers: dict[str, str],
    ) -> tuple[int, dict[str, Any]]:
        return await self._request("POST", cotizacion_id, headers, payload)

    async def consultar_firma(
        self, cotizacion_id: UUID, headers: dict[str, str]
    ) -> tuple[int, dict[str, Any]]:
        return await self._request("GET", cotizacion_id, headers)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        cotizacion_id: UUID,
        headers: dict[str, str],
        payload: bytes | None = None,
    ) -> tuple[int, dict[str, Any]]:
        path = (
            f"/api/v1/insurancepolicies-service/cotizaciones/{cotizacion_id}"
            "/firma-digital"
        )
        try:
            response = await self._client.request(
                method, path, headers=headers, content=payload
            )
        except httpx.HTTPError as exc:
            raise InsurancePoliciesGatewayError(
                503, "El servicio de pólizas no está disponible."
            ) from exc

        try:
            body = response.json()
        except ValueError as exc:
            if response.is_success:
                raise InsurancePoliciesGatewayError(
                    502, "El servicio de pólizas devolvió una respuesta inválida."
                ) from exc
            body = None

        if not response.is_success:
            detail = (
                body.get("detail", "El servicio de pólizas devolvió un error.")
                if isinstance(body, dict)
                else "El servicio de pólizas devolvió un error."
            )
            raise InsurancePoliciesGatewayError(response.status_code, detail)
        if not isinstance(body, dict):
            raise InsurancePoliciesGatewayError(
                502, "El servicio de pólizas devolvió una respuesta inválida."
            )
        return response.status_code, body
