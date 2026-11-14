"""Cliente HTTP hacia MS Siniestros (HU4.1.1). El cliente viaja en `X-Cliente-Id`, nunca desde la app."""
import httpx

from src.core.config import settings

PREFIJO = "/api/v1/insuranceclaims-service"


class ClaimsGatewayError(Exception):
    def __init__(self, status_code: int, detail: str | dict) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class InsuranceClaimsServiceGateway:
    def __init__(
        self,
        base_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url or settings.INSURANCECLAIMS_SERVICE_URL,
            timeout=settings.CLAIMS_TIMEOUT_SECONDS,
            transport=transport,
        )

    async def listar_polizas_elegibles(
        self, cliente_id: str, correlation_id: str, accept_language: str | None = None
    ) -> dict:
        _, body = await self._request(
            "GET", f"{PREFIJO}/siniestros/polizas-elegibles", self._headers(cliente_id, correlation_id, accept_language)
        )
        return body

    async def reportar_siniestro(
        self, cliente_id: str, idempotency_key: str, payload: dict, correlation_id: str
    ) -> tuple[int, dict]:
        """Devuelve el status para distinguir `201` (nuevo) de `200` (reintento con la misma clave)."""
        headers = {**self._headers(cliente_id, correlation_id), "Idempotency-Key": idempotency_key}
        return await self._request("POST", f"{PREFIJO}/siniestros", headers, json=payload)

    async def obtener_siniestro(self, cliente_id: str, siniestro_id: str, correlation_id: str) -> dict:
        _, body = await self._request(
            "GET", f"{PREFIJO}/siniestros/{siniestro_id}", self._headers(cliente_id, correlation_id)
        )
        return body

    async def aclose(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _headers(cliente_id: str, correlation_id: str, accept_language: str | None = None) -> dict[str, str]:
        headers = {"X-Cliente-Id": cliente_id, "X-Correlation-Id": correlation_id}
        if accept_language:
            headers["Accept-Language"] = accept_language
        return headers

    async def _request(self, method: str, path: str, headers: dict, json: dict | None = None) -> tuple[int, dict]:
        try:
            response = await self._client.request(method, path, headers=headers, json=json)
        except httpx.HTTPError as exc:
            raise ClaimsGatewayError(503, "El servicio de siniestros no está disponible.") from exc
        try:
            body = response.json()
        except ValueError:
            body = {}
        if not response.is_success:
            raise ClaimsGatewayError(
                response.status_code, body.get("detail", "El servicio de siniestros devolvió un error.")
            )
        return response.status_code, body
