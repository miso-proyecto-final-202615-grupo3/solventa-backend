import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from src.application.ports.cotizaciones import (
    CoberturaCotizada,
    CondicionesEmision,
    CotizacionEmision,
    CotizacionGateway,
    CotizacionNoEncontradaError,
    ImpuestoCotizado,
    ProductoEmision,
)
from src.application.ports.servicios import ServicioNoDisponibleError
from src.core.config import settings
from src.infrastructure.gateways.http_utils import solicitar_json

_SERVICIO = "quotingengine_service"
_BASE = "/api/v1/quotingengine-service"


def _invalida(detalle: str) -> ServicioNoDisponibleError:
    return ServicioNoDisponibleError(_SERVICIO, detalle)


class QuotingEngineHttpClient(CotizacionGateway):
    """Lee del motor de cotización lo necesario para emitir la póliza."""

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

    async def obtener_cotizacion(
        self, cotizacion_id: uuid.UUID, correlation_id: str
    ) -> CotizacionEmision:
        cuerpo = await solicitar_json(
            self._client,
            _SERVICIO,
            f"{_BASE}/cotizaciones/{cotizacion_id}",
            correlation_id,
            permitir_404=True,
        )
        if cuerpo is None:
            raise CotizacionNoEncontradaError(str(cotizacion_id))
        try:
            return CotizacionEmision(
                cotizacion_id=uuid.UUID(cuerpo["cotizacion_id"]),
                cliente_id=uuid.UUID(cuerpo["cliente_id"]),
                producto_codigo=str(cuerpo["producto_codigo"]),
                moneda=str(cuerpo["moneda"]),
                prima_base=Decimal(str(cuerpo["prima_base"])),
                prima_neta=Decimal(str(cuerpo["prima_neta"])),
                prima_total=Decimal(str(cuerpo["prima_total"])),
                impuestos=tuple(
                    ImpuestoCotizado(
                        concepto=str(i["concepto"]),
                        tasa=Decimal(str(i["tasa"])),
                        valor=Decimal(str(i["valor"])),
                    )
                    for i in cuerpo.get("impuestos", [])
                ),
                coberturas=tuple(
                    CoberturaCotizada(
                        cobertura_id=uuid.UUID(c["cobertura_id"]),
                        codigo=str(c["codigo"]),
                        nombre=str(c["nombre"]),
                        prima=Decimal(str(c["prima"])),
                        limite_asegurado=Decimal(str(c["limite_asegurado"])),
                        deducible=Decimal(str(c["deducible"])),
                    )
                    for c in cuerpo["coberturas"]
                ),
            )
        except (KeyError, ValueError, TypeError, InvalidOperation) as exc:
            raise _invalida("cotización inválida") from exc

    async def obtener_producto(self, codigo: str, correlation_id: str) -> ProductoEmision:
        cuerpo = await solicitar_json(
            self._client, _SERVICIO, f"{_BASE}/productos/{codigo}", correlation_id
        )
        try:
            return ProductoEmision(
                producto_id=uuid.UUID(cuerpo["producto_id"]),
                codigo=str(cuerpo["codigo"]),
                nombre=str(cuerpo["nombre"]),
                ramo=str(cuerpo["ramo"]),
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise _invalida("producto inválido") from exc

    async def obtener_condiciones(
        self, cotizacion_id: uuid.UUID, correlation_id: str
    ) -> CondicionesEmision:
        cuerpo = await solicitar_json(
            self._client,
            _SERVICIO,
            f"{_BASE}/cotizaciones/{cotizacion_id}/condiciones",
            correlation_id,
        )
        try:
            particulares = cuerpo["condiciones_particulares"]
            if not isinstance(particulares, dict):
                raise TypeError("condiciones_particulares")
            return CondicionesEmision(
                version_condiciones_generales=str(cuerpo["version_condiciones_generales"]),
                condiciones_particulares=particulares,
                aceptadas_en=self._aceptadas_en(cuerpo.get("ultima_decision")),
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise _invalida("condiciones inválidas") from exc

    @staticmethod
    def _aceptadas_en(decision: Any) -> datetime | None:
        if isinstance(decision, dict) and decision.get("decision") == "ACEPTADA":
            return datetime.fromisoformat(decision["decidida_en"])
        return None
