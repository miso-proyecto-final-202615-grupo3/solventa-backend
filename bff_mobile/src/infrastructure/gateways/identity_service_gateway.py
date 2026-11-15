import httpx

from src.core.config import settings


class IdentityGatewayError(Exception):
    def __init__(self, status_code: int, detail: str | dict) -> None:
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

    async def renovar_sesion(self, refresh_token: str) -> dict:
        return await self._post(
            "/api/v1/identity-service/clientes/renovar-sesion",
            {"refresh_token": refresh_token},
        )

    async def obtener_resumen_movil(
        self, correo: str, installation_id: str | None
    ) -> dict:
        try:
            response = await self._client.get(
                "/api/v1/identity-service/clientes/resumen-movil",
                params={"correo": correo, "installation_id": installation_id},
            )
        except httpx.HTTPError as exc:
            raise IdentityGatewayError(503, "El servicio de identidad no está disponible.") from exc
        try:
            body = response.json()
        except ValueError:
            body = {}
        if not response.is_success:
            raise IdentityGatewayError(response.status_code, body.get("detail", "El servicio de identidad devolvió un error."))
        return body

    async def obtener_cliente_id(self, correo: str, correlation_id: str) -> str:
        """`id` del cliente dueño del correo (HU4.1.1). Sin `installation_id`: solo interesa el cliente."""
        try:
            response = await self._client.get(
                "/api/v1/identity-service/clientes/resumen-movil",
                params={"correo": correo},
                headers={"X-Correlation-Id": correlation_id},
            )
        except httpx.HTTPError as exc:
            raise IdentityGatewayError(503, "El servicio de identidad no está disponible.") from exc
        try:
            body = response.json()
        except ValueError:
            body = {}
        if not response.is_success:
            raise IdentityGatewayError(response.status_code, body.get("detail", "El servicio de identidad devolvió un error."))
        if not body.get("id"):
            raise IdentityGatewayError(503, "El servicio de identidad devolvió una respuesta inválida.")
        return str(body["id"])

    async def iniciar_activacion_movil(
        self,
        correo: str,
        dispositivo: dict,
        correlation_id: str,
    ) -> dict:
        return await self._post(
            "/api/v1/identity-service/clientes/activacion-movil/sesiones",
            {"correo": correo, **dispositivo},
            headers={"X-Correlation-Id": correlation_id},
            timeout=settings.ACTIVATION_TIMEOUT_SECONDS,
        )

    async def verificar_activacion_movil(self, sesion_id: str, correo: str, metadata: str, frames: dict[str, bytes], correlation_id: str) -> dict:
        try:
            response = await self._client.post(
                f"/api/v1/identity-service/clientes/activacion-movil/sesiones/{sesion_id}/verificacion",
                data={"correo": correo, "metadata": metadata},
                files={key: (f"{key}.jpg", value, "image/jpeg") for key, value in frames.items()} or None,
                headers={"X-Correlation-Id": correlation_id},
                timeout=settings.ACTIVATION_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:
            raise IdentityGatewayError(503, "El servicio de identidad no está disponible.") from exc
        try:
            body = response.json()
        except ValueError:
            body = {}
        if not response.is_success:
            raise IdentityGatewayError(response.status_code, body.get("detail", "El servicio de identidad devolvió un error."))
        return body

    async def consultar_consentimiento_biometrico(self, correo: str, correlation_id: str) -> dict:
        try:
            response = await self._client.get(
                "/api/v1/identity-service/clientes/consentimiento-biometrico",
                params={"correo": correo},
                headers={"X-Correlation-Id": correlation_id},
            )
        except httpx.HTTPError as exc:
            raise IdentityGatewayError(503, "El servicio de identidad no está disponible.") from exc
        try:
            body = response.json()
        except ValueError:
            body = {}
        if not response.is_success:
            raise IdentityGatewayError(response.status_code, body.get("detail", "El servicio de identidad devolvió un error."))
        return body

    async def registrar_consentimiento_biometrico(self, correo: str, decision: dict, correlation_id: str) -> dict:
        return await self._post(
            "/api/v1/identity-service/clientes/consentimiento-biometrico",
            {"correo": correo, **decision},
            headers={"X-Correlation-Id": correlation_id},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _post(
        self,
        path: str,
        payload: dict,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> dict:
        try:
            response = await self._client.post(
                path, json=payload, headers=headers, timeout=timeout or self._client.timeout
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
