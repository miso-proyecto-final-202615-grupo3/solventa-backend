import httpx

from src.application.ports import (
    ProviderSessionStarted,
    ProviderUnavailableError,
    ProviderVerificationResult,
)
from src.core.config import settings

_PENDING_STATUSES = {"Not Started", "In Progress", "In Review", "Resubmitted", "Awaiting User"}


class DiditProvider:
    """Estrategia contra la API de sesiones de Didit (o `mock_kyc`, que imita su contrato).

    Solo para demostración: se registra con `DIDIT_ENABLED=true` y el adaptador limita su uso
    con topes diarios y mensuales para no salir de la cuota gratuita.
    """

    name = "didit"
    capture_type = "SDK"
    requires_budget = True

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        workflow_id: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.DIDIT_API_KEY
        self._workflow_id = workflow_id if workflow_id is not None else settings.DIDIT_WORKFLOW_ID
        self._client = httpx.Client(
            base_url=(base_url or settings.DIDIT_BASE_URL).rstrip("/"),
            timeout=settings.DIDIT_TIMEOUT_SECONDS,
            transport=transport,
        )

    def start_session(self, customer_id: str, session_id: str) -> ProviderSessionStarted:
        body = self._request(
            "POST",
            "/v3/session/",
            json={
                "workflow_id": self._workflow_id,
                "vendor_data": customer_id,
                "metadata": {"session_id": session_id},
            },
        )
        token = body.get("session_token")
        provider_session_id = body.get("session_id")
        if not isinstance(token, str) or not isinstance(provider_session_id, str):
            raise ProviderUnavailableError()
        return ProviderSessionStarted(
            capture={"tipo": "SDK", "sdk": {"nombre": "DIDIT", "session_token": token}},
            provider_session_id=provider_session_id,
        )

    def verify(
        self, session: dict, frames: dict[str, bytes], sdk_result: str | None
    ) -> ProviderVerificationResult:
        provider_session_id = session.get("provider_session_id")
        if not provider_session_id:
            raise ProviderUnavailableError()
        body = self._request("GET", f"/v3/session/{provider_session_id}/decision/")
        decision = body.get("status")
        if decision == "Approved":
            return ProviderVerificationResult(provider_session_id, True)
        if decision == "Declined":
            return ProviderVerificationResult(provider_session_id, False, "PRUEBA_VIDA_FALLIDA")
        if decision in _PENDING_STATUSES:
            raise ProviderUnavailableError()
        raise ProviderUnavailableError()

    def _request(self, method: str, path: str, **kwargs) -> dict:
        try:
            response = self._client.request(
                method, path, headers={"x-api-key": self._api_key}, **kwargs
            )
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError() from exc
        # 400 por créditos insuficientes, 429 por límite o 5xx: no consumen intento.
        if not response.is_success:
            raise ProviderUnavailableError()
        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderUnavailableError() from exc
        if not isinstance(body, dict):
            raise ProviderUnavailableError()
        return body
