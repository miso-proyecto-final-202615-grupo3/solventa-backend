import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation

import httpx

from src.application.ports.cotizaciones import (
    CotizacionGateway,
    CotizacionNoEncontradaError,
    CotizacionPago,
)
from src.application.ports.servicios import ServicioNoDisponibleError
from src.core.config import settings
from src.infrastructure.gateways.http_utils import solicitar_json

_SERVICIO = "quotingengine_service"
_BASE = "/api/v1/quotingengine-service/cotizaciones"


class QuotingEngineHttpClient(CotizacionGateway):
    """Lee la cotización y la decisión sobre sus condiciones del motor de cotización."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url or settings.QUOTINGENGINE_SERVICE_URL,
            timeout=timeout or settings.SERVICES_TIMEOUT_SECONDS,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def obtener(self, cotizacion_id: uuid.UUID, correlation_id: str) -> CotizacionPago:
        cuerpo = await solicitar_json(
            self._client, _SERVICIO, f"{_BASE}/{cotizacion_id}", correlation_id, permitir_404=True
        )
        if cuerpo is None:
            raise CotizacionNoEncontradaError(str(cotizacion_id))
        try:
            expira_en = datetime.fromisoformat(cuerpo["expira_en"])
            if expira_en.tzinfo is None:
                raise ValueError("expira_en sin zona horaria")
            return CotizacionPago(
                cotizacion_id=uuid.UUID(cuerpo["cotizacion_id"]),
                cliente_id=uuid.UUID(cuerpo["cliente_id"]),
                estado=str(cuerpo["estado"]),
                prima_total=Decimal(str(cuerpo["prima_total"])),
                moneda=str(cuerpo["moneda"]),
                expira_en=expira_en,
            )
        except (KeyError, ValueError, TypeError, InvalidOperation) as exc:
            raise ServicioNoDisponibleError(_SERVICIO, "cotización inválida") from exc

    async def condiciones_aceptadas(self, cotizacion_id: uuid.UUID, correlation_id: str) -> bool:
        cuerpo = await solicitar_json(
            self._client,
            _SERVICIO,
            f"{_BASE}/{cotizacion_id}/condiciones",
            correlation_id,
            permitir_404=True,
        )
        if cuerpo is None:
            return False
        decision = cuerpo.get("ultima_decision")
        return isinstance(decision, dict) and decision.get("decision") == "ACEPTADA"
