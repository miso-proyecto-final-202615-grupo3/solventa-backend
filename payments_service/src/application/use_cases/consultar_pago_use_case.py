import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from src.application.ports.cotizaciones import CotizacionGateway, CotizacionPago
from src.application.use_cases.procesar_pago_prima_use_case import (
    COTIZACION_VIGENTE,
    CotizacionNoVigenteError,
    PagoNoEncontradoError,
)
from src.domain.pagos.entities import METODO_PAGO_DEFECTO, MetodoPago, PagoPrima
from src.domain.pagos.repositories import PagoPrimaRepository


@dataclass(frozen=True)
class ResumenPago:
    cotizacion: CotizacionPago
    metodos_pago: tuple[MetodoPago, ...] = tuple(MetodoPago)
    metodo_por_defecto: MetodoPago = METODO_PAGO_DEFECTO


class ConsultarResumenPagoUseCase:
    """Presenta el valor de la prima a pagar y los métodos de pago disponibles."""

    def __init__(self, cotizaciones: CotizacionGateway) -> None:
        self.cotizaciones = cotizaciones

    async def ejecutar(self, cotizacion_id: uuid.UUID, correlation_id: str) -> ResumenPago:
        cotizacion = await self.cotizaciones.obtener(cotizacion_id, correlation_id)
        if cotizacion.estado != COTIZACION_VIGENTE or cotizacion.expira_en <= datetime.now(UTC):
            raise CotizacionNoVigenteError("La cotización no está vigente.")
        return ResumenPago(cotizacion=cotizacion)


class ConsultarPagoUseCase:
    def __init__(self, pagos: PagoPrimaRepository) -> None:
        self.pagos = pagos

    async def ejecutar(self, pago_id: uuid.UUID) -> PagoPrima:
        pago = await self.pagos.obtener_por_id(pago_id)
        if pago is None:
            raise PagoNoEncontradoError(str(pago_id))
        return pago
