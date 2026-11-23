from typing import Any

import httpx


class BackendGatewayError(Exception):
    def __init__(self, status_code: int, detail: Any) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(str(detail))


class BackendGateway:
    def __init__(self, client: httpx.AsyncClient, base_url: str, prefix: str) -> None:
        self.client = client
        self.base_url = base_url
        self.prefix = prefix

    async def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            return await self.client.request(
                method, f"{self.base_url}{self.prefix}{path}", **kwargs
            )
        except httpx.HTTPError as exc:
            raise BackendGatewayError(503, "Servicio de backend no disponible.") from exc


def json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        result = response.json()
    except ValueError as exc:
        raise BackendGatewayError(502, "Respuesta inválida del servicio de backend.") from exc
    if not isinstance(result, dict):
        raise BackendGatewayError(502, "Respuesta inválida del servicio de backend.")
    if not response.is_success:
        raise BackendGatewayError(
            response.status_code, result.get("detail", "Error del servicio de backend.")
        )
    return result
