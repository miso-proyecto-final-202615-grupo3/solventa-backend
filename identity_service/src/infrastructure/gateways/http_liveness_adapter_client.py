import httpx

from src.application.ports.liveness import (
    LivenessAdapterUnavailableError,
    LivenessSessionInfo,
    LivenessVerificationPort,
)
from src.core.config import settings


class HttpLivenessAdapterClient(LivenessVerificationPort):
    """Cliente interno; Identity no conoce proveedores ni detalles de captura."""

    def __init__(self, base_url: str | None = None, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url or settings.LIVENESS_ADAPTER_URL,
            timeout=settings.LIVENESS_ADAPTER_TIMEOUT_SECONDS,
            transport=transport,
        )

    async def start_session(self, customer_id: str, correlation_id: str) -> LivenessSessionInfo:
        try:
            response = await self._client.post(
                "/api/v1/liveness-adapter/liveness/sessions",
                json={"customer_id": customer_id},
                headers={"X-Correlation-Id": correlation_id},
            )
            response.raise_for_status()
            body = response.json()
            return LivenessSessionInfo(body["session_id"], body["expires_at"], body["capture"])
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise LivenessAdapterUnavailableError() from exc

    async def aclose(self) -> None:
        await self._client.aclose()
