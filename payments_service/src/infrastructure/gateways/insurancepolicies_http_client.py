import uuid

import httpx

from src.application.ports.firmas import FirmaGateway, FirmaPago
from src.application.ports.servicios import ServicioNoDisponibleError
from src.core.config import settings
from src.infrastructure.gateways.http_utils import solicitar_json

_SERVICIO = "insurancepolicies_service"


class InsurancePoliciesHttpClient(FirmaGateway):
    """Consulta la firma digital vigente de la cotización en el servicio de pólizas."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url or settings.INSURANCEPOLICIES_SERVICE_URL,
            timeout=timeout or settings.SERVICES_TIMEOUT_SECONDS,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def obtener_vigente(
        self, cotizacion_id: uuid.UUID, correlation_id: str
    ) -> FirmaPago | None:
        cuerpo = await solicitar_json(
            self._client,
            _SERVICIO,
            f"/api/v1/insurancepolicies-service/cotizaciones/{cotizacion_id}/firma-digital",
            correlation_id,
            permitir_404=True,
        )
        if cuerpo is None:
            return None
        try:
            return FirmaPago(
                firma_id=uuid.UUID(cuerpo["firma_id"]),
                cliente_id=uuid.UUID(cuerpo["cliente_id"]),
                estado=str(cuerpo["estado"]),
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise ServicioNoDisponibleError(_SERVICIO, "firma inválida") from exc
