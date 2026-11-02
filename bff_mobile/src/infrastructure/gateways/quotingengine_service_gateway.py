from typing import Any

import httpx

from src.core.config import settings


class QuotingEngineGatewayError(Exception):
    def __init__(self, status_code: int, detail: Any) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(str(detail))


class QuotingEngineServiceGateway:
    """Cliente HTTP hacia el servicio de cotización."""

    def __init__(
        self,
        base_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url or settings.QUOTINGENGINE_SERVICE_URL,
            timeout=5.0,
            transport=transport,
        )

    async def listar_productos(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/api/v1/quotingengine-service/productos")

    async def obtener_producto(self, codigo: str) -> dict[str, Any]:
        return await self._request(
            "GET", f"/api/v1/quotingengine-service/productos/{codigo}"
        )

    async def solicitar_cotizacion(
        self, payload: bytes, content_type: str = "application/json"
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/v1/quotingengine-service/cotizaciones",
            payload,
            content_type,
        )

    async def obtener_cotizacion(self, cotizacion_id: str) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/api/v1/quotingengine-service/cotizaciones/{cotizacion_id}",
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        payload: bytes | None = None,
        content_type: str = "application/json",
    ) -> Any:
        try:
            kwargs = (
                {
                    "content": payload,
                    "headers": {"content-type": content_type},
                }
                if payload is not None
                else {}
            )
            response = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise QuotingEngineGatewayError(
                status_code=503,
                detail="El servicio de cotización no está disponible.",
            ) from exc

        try:
            body = response.json()
        except ValueError as exc:
            if response.is_success:
                raise QuotingEngineGatewayError(
                    status_code=502,
                    detail="El servicio de cotización devolvió una respuesta inválida.",
                ) from exc
            body = None

        if not response.is_success:
            detail = (
                body.get("detail", "El servicio de cotización devolvió un error.")
                if isinstance(body, dict)
                else body or "El servicio de cotización devolvió un error."
            )
            raise QuotingEngineGatewayError(
                status_code=response.status_code,
                detail=detail,
            )

        return body
