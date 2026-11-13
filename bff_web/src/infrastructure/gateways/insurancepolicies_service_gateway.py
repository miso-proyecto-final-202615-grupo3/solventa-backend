from typing import Any
from uuid import UUID

import httpx

from src.core.config import settings

_PREFIJO = "/api/v1/insurancepolicies-service"
MAX_CERTIFICADO_BYTES = 10 * 1024 * 1024


class InsurancePoliciesGatewayError(Exception):
    def __init__(self, status_code: int, detail: Any) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(str(detail))


class InsurancePoliciesServiceGateway:
    """Cliente HTTP para consulta de pólizas y firma digital."""

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

    async def listar_mis_polizas(self, client_id: str) -> list[dict[str, Any]]:
        body = await self._request_poliza(
            "GET", "/polizas/mis-polizas", {"X-Client-Id": client_id}
        )
        return body

    async def obtener_poliza(self, poliza_id: str, client_id: str) -> dict[str, Any]:
        return await self._request_poliza(
            "GET", f"/polizas/{poliza_id}", {"X-Client-Id": client_id}
        )

    async def capturar_firma(
        self,
        cotizacion_id: UUID,
        payload: bytes,
        headers: dict[str, str],
    ) -> tuple[int, dict[str, Any]]:
        return await self._request_firma("POST", cotizacion_id, headers, payload)

    async def consultar_firma(
        self, cotizacion_id: UUID, headers: dict[str, str]
    ) -> tuple[int, dict[str, Any]]:
        return await self._request_firma("GET", cotizacion_id, headers)

    async def consultar_poliza_por_cotizacion(
        self, cotizacion_id: UUID, headers: dict[str, str]
    ) -> dict[str, Any]:
        return await self._request_poliza(
            "GET", f"{_PREFIJO}/cotizaciones/{cotizacion_id}/poliza", headers
        )

    async def consultar_estado_certificado(
        self, poliza_id: UUID, headers: dict[str, str]
    ) -> dict[str, Any]:
        return await self._request_poliza(
            "GET", f"{_PREFIJO}/polizas/{poliza_id}/certificado", headers
        )

    async def descargar_certificado(
        self, poliza_id: UUID, headers: dict[str, str]
    ) -> tuple[bytes, str | None]:
        """PDF del certificado y el Content-Disposition que propone el servicio de pólizas."""
        try:
            response = await self._client.get(
                f"{_PREFIJO}/polizas/{poliza_id}/certificado/descarga", headers=headers
            )
        except httpx.HTTPError as exc:
            raise InsurancePoliciesGatewayError(
                503, "El servicio de pólizas no está disponible."
            ) from exc

        if not response.is_success:
            try:
                body = response.json()
            except ValueError:
                body = None
            self._raise_response_error(response, body)
        tipo = response.headers.get("content-type", "").split(";")[0].strip().lower()
        if tipo != "application/pdf" or len(response.content) > MAX_CERTIFICADO_BYTES:
            raise InsurancePoliciesGatewayError(
                502, "El servicio de pólizas devolvió un certificado inválido."
            )
        return response.content, response.headers.get("content-disposition")

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request_poliza(
        self, method: str, path: str, headers: dict[str, str]
    ) -> Any:
        try:
            response = await self._client.request(method, path, headers=headers)
        except httpx.HTTPError as exc:
            raise InsurancePoliciesGatewayError(
                503, "El servicio de pólizas no está disponible."
            ) from exc

        body = self._parse_body(response)
        if not response.is_success:
            self._raise_response_error(response, body)
        return body

    async def _request_firma(
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

        body = self._parse_body(response)
        if not response.is_success:
            self._raise_response_error(response, body)
        if not isinstance(body, dict):
            raise InsurancePoliciesGatewayError(
                502, "El servicio de pólizas devolvió una respuesta inválida."
            )
        return response.status_code, body

    @staticmethod
    def _parse_body(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            if response.is_success:
                raise InsurancePoliciesGatewayError(
                    502, "El servicio de pólizas devolvió una respuesta inválida."
                ) from exc
            return None

    @staticmethod
    def _raise_response_error(response: httpx.Response, body: Any) -> None:
        detail = (
            body.get("detail", "El servicio de pólizas devolvió un error.")
            if isinstance(body, dict)
            else body or "El servicio de pólizas devolvió un error."
        )
        raise InsurancePoliciesGatewayError(response.status_code, detail)
