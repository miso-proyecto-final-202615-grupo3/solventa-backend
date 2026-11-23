from typing import Any

import httpx

from src.core.config import settings

_PREFIJO = "/api/v1/insurancepolicies-service/polizas"
MAX_CERTIFICADO_BYTES = 10 * 1024 * 1024


class PoliciesGatewayError(Exception):
    def __init__(self, status_code: int, detail: Any) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(str(detail))


class InsurancePoliciesServiceGateway:
    """Cliente HTTP hacia MS Pólizas para la billetera de la app (HU3.2.x)."""

    def __init__(
        self,
        base_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url or settings.INSURANCEPOLICIES_SERVICE_URL,
            timeout=timeout_seconds or settings.POLICIES_TIMEOUT_SECONDS,
            transport=transport,
        )

    async def listar_mis_polizas(self, cliente_id: str, correlation_id: str) -> list[dict[str, Any]]:
        body = await self._get_json(f"{_PREFIJO}/mis-polizas", cliente_id, correlation_id)
        if not isinstance(body, list):
            raise PoliciesGatewayError(502, "MS Pólizas devolvió una respuesta inválida.")
        return body

    async def descargar_certificado(
        self, poliza_id: str, cliente_id: str, correlation_id: str
    ) -> tuple[bytes, str | None]:
        """PDF del certificado y el `Content-Disposition` que propone MS Pólizas."""
        try:
            response = await self._client.get(
                f"{_PREFIJO}/{poliza_id}/certificado/descarga",
                headers=self._headers(cliente_id, correlation_id),
            )
        except httpx.HTTPError as exc:
            raise PoliciesGatewayError(503, "MS Pólizas no está disponible.") from exc
        if not response.is_success:
            raise PoliciesGatewayError(response.status_code, self._detalle(response))
        tipo = response.headers.get("content-type", "").split(";")[0].strip().lower()
        if tipo != "application/pdf" or len(response.content) > MAX_CERTIFICADO_BYTES:
            raise PoliciesGatewayError(502, "MS Pólizas devolvió un certificado inválido.")
        return response.content, response.headers.get("content-disposition")

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get_json(self, path: str, cliente_id: str, correlation_id: str) -> Any:
        try:
            response = await self._client.get(path, headers=self._headers(cliente_id, correlation_id))
        except httpx.HTTPError as exc:
            raise PoliciesGatewayError(503, "MS Pólizas no está disponible.") from exc
        if not response.is_success:
            raise PoliciesGatewayError(response.status_code, self._detalle(response))
        try:
            return response.json()
        except ValueError as exc:
            raise PoliciesGatewayError(502, "MS Pólizas devolvió una respuesta inválida.") from exc

    @staticmethod
    def _headers(cliente_id: str, correlation_id: str) -> dict[str, str]:
        return {"X-Client-Id": cliente_id, "X-Correlation-Id": correlation_id}

    @staticmethod
    def _detalle(response: httpx.Response) -> Any:
        try:
            body = response.json()
        except ValueError:
            return None
        return body.get("detail") if isinstance(body, dict) else None
