import httpx

from src.core.config import settings


class IdentityGatewayError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class IdentityServiceGateway:
    """Cliente HTTP hacia el MS Identidad."""

    def __init__(
        self,
        base_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url or settings.IDENTITY_SERVICE_URL
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=settings.IDENTITY_TIMEOUT_SECONDS,
            transport=transport,
        )

    async def autenticar_cliente(self, correo: str, password: str) -> dict:
        return await self._post(
            "/api/v1/identity-service/clientes/autenticar",
            {"correo": correo, "password": password},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _post(self, path: str, payload: dict) -> dict:
        try:
            response = await self._client.post(path, json=payload)
        except httpx.HTTPError as exc:
            raise IdentityGatewayError(
                status_code=503,
                detail="El servicio de identidad no está disponible.",
            ) from exc

        try:
            body = response.json()
        except ValueError:
            body = {}

        if not response.is_success:
            raise IdentityGatewayError(
                status_code=response.status_code,
                detail=body.get(
                    "detail", "El servicio de identidad devolvió un error."
                ),
            )

        return body
