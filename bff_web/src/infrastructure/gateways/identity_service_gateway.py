import httpx

from src.core.config import settings


# Subida de documentos: identity almacena en S3 y llama al proveedor KYC/AML.
UPLOAD_TIMEOUT_SECONDS = 30.0


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

    async def iniciar_verificacion_kyc_aml(
        self,
        cliente_id: str,
        payload: bytes,
        content_type: str,
        headers: dict[str, str] | None = None,
    ) -> dict:
        return await self._request(
            "POST",
            f"/api/v1/identity-service/clientes/{cliente_id}/verificaciones-kyc-aml",
            payload,
            content_type,
            headers=headers,
            timeout=UPLOAD_TIMEOUT_SECONDS,
        )

    async def consultar_verificacion_kyc_aml(
        self,
        cliente_id: str,
        verificacion_id: str,
        headers: dict[str, str] | None = None,
    ) -> dict:
        return await self._request(
            "GET",
            f"/api/v1/identity-service/clientes/{cliente_id}"
            f"/verificaciones-kyc-aml/{verificacion_id}",
            headers=headers,
            timeout=UPLOAD_TIMEOUT_SECONDS,
        )

    async def consultar_auditoria_consentimiento(
        self, params: dict[str, str]
    ) -> dict:
        return await self._request(
            "GET",
            "/api/v1/identity-service/consentimientos",
            params=params,
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
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> dict:
        try:
            request_headers = dict(headers or {})
            kwargs: dict = {}
            if payload is not None:
                kwargs["content"] = payload
                request_headers["content-type"] = content_type
            if timeout is not None:
                kwargs["timeout"] = timeout
            response = await self._client.request(
                method, path, params=params, headers=request_headers, **kwargs
            )
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