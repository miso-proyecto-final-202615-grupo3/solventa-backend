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
            base_url=self.base_url, timeout=5.0, transport=transport
        )

    async def registrar_cliente(
        self, payload: bytes, content_type: str = "application/json"
    ) -> dict:
        return await self._post(
            "/api/v1/identity-service/clientes/registro", payload, content_type
        )

    async def autenticar_cliente(
        self, payload: bytes, content_type: str = "application/json"
    ) -> dict:
        return await self._post(
            "/api/v1/identity-service/clientes/autenticar", payload, content_type
        )

    async def actualizar_consentimiento(
        self,
        cliente_id: str,
        payload: bytes,
        content_type: str = "application/json",
    ) -> dict:
        return await self._request(
            "PUT",
            f"/api/v1/identity-service/clientes/{cliente_id}/consentimiento",
            payload,
            content_type,
        )

    async def obtener_perfil_cliente(self, cliente_id: str) -> dict:
        return await self._request(
            "GET",
            f"/api/v1/identity-service/clientes/{cliente_id}/perfil",
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _post(self, path: str, payload: bytes, content_type: str) -> dict:
        return await self._request("POST", path, payload, content_type)

    async def _request(
        self,
        method: str,
        path: str,
        payload: bytes | None = None,
        content_type: str = "application/json",
    ) -> dict:
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