from typing import Any

import httpx

from src.core.config import settings

_SOCIOS = "/api/v1/identity-service/socios"


class IdentitySociosGatewayError(Exception):
    def __init__(self, status_code: int, detail: Any) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(str(detail))


class IdentitySociosGateway:
    def __init__(
        self,
        base_url: str | None = None,
        internal_token: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url or settings.IDENTITY_SERVICE_URL
        self.internal_token = internal_token
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=5.0, transport=transport)

    async def registrar_socio(
        self,
        payload: dict[str, str],
        actor_id: str,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        headers = {"X-Actor-Id": actor_id}
        if correlation_id:
            headers["X-Correlation-Id"] = correlation_id
        try:
            response = await self._client.post(_SOCIOS, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise IdentitySociosGatewayError(
                503, "El servicio de socios no está disponible."
            ) from exc

        try:
            body = response.json()
        except ValueError:
            body = None
        if not response.is_success:
            detail = (
                body.get("detail", "El servicio de socios devolvió un error.")
                if isinstance(body, dict)
                else "El servicio de socios devolvió un error."
            )
            raise IdentitySociosGatewayError(response.status_code, detail)
        if not isinstance(body, dict):
            raise IdentitySociosGatewayError(
                502, "El servicio de socios devolvió una respuesta inválida."
            )
        return body

    async def listar_socios(self, actor_id: str, correlation_id: str | None = None) -> list[dict[str, Any]]:
        headers = {"X-Actor-Id": actor_id}
        if correlation_id:
            headers["X-Correlation-Id"] = correlation_id
        try:
            response = await self._client.get(_SOCIOS, headers=headers)
        except httpx.HTTPError as exc:
            raise IdentitySociosGatewayError(503, "El servicio de socios no está disponible.") from exc
        if not response.is_success:
            body = response.json()
            detail = body.get("detail", "El servicio de socios devolvió un error.") if isinstance(body, dict) else "El servicio de socios devolvió un error."
            raise IdentitySociosGatewayError(response.status_code, detail)
        return response.json()

    async def aclose(self) -> None:
        await self._client.aclose()
