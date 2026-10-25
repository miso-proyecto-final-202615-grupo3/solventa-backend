import httpx

from src.core.config import settings


class CotizacionGatewayError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class CotizacionServiceGateway:
    def __init__(
        self,
        base_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url or settings.MOTOR_COTIZACION_URL,
            timeout=1.0,
            transport=transport,
        )

    async def cotizar(
        self,
        payload: bytes,
        content_type: str = "application/json",
    ) -> dict:
        try:
            response = await self._client.post(
                "/api/v1/motor-cotizacion/cotizar",
                content=payload,
                headers={"content-type": content_type},
            )
        except httpx.HTTPError as exc:
            raise CotizacionGatewayError(
                status_code=503,
                detail="El motor de cotización no está disponible.",
            ) from exc

        try:
            body = response.json()
        except ValueError:
            body = {}

        if not response.is_success:
            raise CotizacionGatewayError(
                status_code=response.status_code,
                detail=body.get(
                    "detail", "El motor de cotización devolvió un error."
                ),
            )
        return body

    async def aclose(self) -> None:
        await self._client.aclose()
