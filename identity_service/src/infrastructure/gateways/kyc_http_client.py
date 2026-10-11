import httpx

from src.application.ports.kyc import KycVerifier
from src.core.config import settings
from src.domain.clientes.value_objects import EstadoKYC

_STATUS_TO_KYC = {
    "PASSED": EstadoKYC.VALIDADO,
    "FAILED": EstadoKYC.RECHAZADO,
    "PENDING": EstadoKYC.PENDIENTE,
}


class KycHttpClient(KycVerifier):
    """Consume el proveedor (o mock) de KYC.

    Si el proveedor falla o supera el timeout se degrada a PENDIENTE
    (disponibilidad: no rompe el journey).
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url or settings.KYC_SERVICE_URL
        self.timeout = timeout or settings.KYC_TIMEOUT_SECONDS
        self._client = httpx.AsyncClient(
            base_url=self.base_url, timeout=self.timeout, transport=transport
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def verificar(
        self, tipo_documento: str, numero_identificacion: str
    ) -> EstadoKYC:
        try:
            response = await self._client.post(
                "/verify",
                json={
                    "document_type": tipo_documento,
                    "document_number": numero_identificacion,
                },
            )
        except httpx.HTTPError:
            return EstadoKYC.PENDIENTE

        if response.status_code >= 400:
            return EstadoKYC.PENDIENTE

        try:
            estado = response.json().get("status")
        except ValueError:
            return EstadoKYC.PENDIENTE

        return _STATUS_TO_KYC.get(estado, EstadoKYC.PENDIENTE)