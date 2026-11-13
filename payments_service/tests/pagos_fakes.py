"""Dobles de prueba en memoria para el pago de la prima."""
import copy
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from src.application.ports.cotizaciones import (
    CotizacionGateway,
    CotizacionNoEncontradaError,
    CotizacionPago,
)
from src.application.ports.firmas import FirmaGateway, FirmaPago
from src.application.ports.proveedor_pago import (
    DatosTarjeta,
    ProveedorPago,
    ProveedorTarjeta,
    ResultadoCobro,
    SolicitudCobro,
)
from src.domain.eventos.entities import EventoOutbox
from src.domain.eventos.repositories import EventoOutboxRepository
from src.domain.pagos.entities import ESTADOS_PAGO_ACTIVO, PagoPrima
from src.domain.pagos.repositories import PagoDuplicadoError, PagoPrimaRepository

COTIZACION_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
CLIENTE_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
AHORA = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)


def cotizacion(**cambios) -> CotizacionPago:
    valores = {
        "cotizacion_id": COTIZACION_ID,
        "cliente_id": CLIENTE_ID,
        "estado": "VIGENTE",
        "prima_total": Decimal("1250000.505"),
        "moneda": "COP",
        "expira_en": AHORA + timedelta(days=5),
    }
    return CotizacionPago(**{**valores, **cambios})


class RepoPagosEnMemoria(PagoPrimaRepository):
    def __init__(self) -> None:
        self.pagos: dict[uuid.UUID, PagoPrima] = {}
        self.fallar_actualizacion = False

    async def crear(self, pago: PagoPrima) -> None:
        for otro in self.pagos.values():
            misma_clave = (otro.cliente_id, otro.idempotency_key) == (
                pago.cliente_id,
                pago.idempotency_key,
            )
            activo = (
                otro.cotizacion_id == pago.cotizacion_id
                and otro.estado in ESTADOS_PAGO_ACTIVO
                and pago.estado in ESTADOS_PAGO_ACTIVO
            )
            if misma_clave or activo:
                raise PagoDuplicadoError()
        self.pagos[pago.pago_id] = copy.copy(pago)

    async def obtener_por_id(self, pago_id):
        pago = self.pagos.get(pago_id)
        return copy.copy(pago) if pago else None

    async def obtener_por_idempotency_key(self, cliente_id, idempotency_key):
        for pago in self.pagos.values():
            if (pago.cliente_id, pago.idempotency_key) == (cliente_id, idempotency_key):
                return copy.copy(pago)
        return None

    async def obtener_activo_por_cotizacion(self, cotizacion_id):
        for pago in self.pagos.values():
            if pago.cotizacion_id == cotizacion_id and pago.estado in ESTADOS_PAGO_ACTIVO:
                return copy.copy(pago)
        return None

    async def actualizar(self, pago: PagoPrima) -> bool:
        guardado = self.pagos.get(pago.pago_id)
        if self.fallar_actualizacion or guardado is None or guardado.version != pago.version:
            return False
        pago.version += 1
        self.pagos[pago.pago_id] = copy.copy(pago)
        return True


class EventosEnMemoria(EventoOutboxRepository):
    def __init__(self) -> None:
        self.eventos: list[EventoOutbox] = []

    async def agregar(self, evento):
        self.eventos.append(evento)

    async def obtener_pendientes(self, limite):
        return self.eventos[:limite]

    async def marcar_publicado(self, evento_id, cuando):
        raise NotImplementedError

    async def registrar_fallo(self, evento_id, detalle):
        raise NotImplementedError


class CotizacionesFalsas(CotizacionGateway):
    def __init__(self, cotizacion_: CotizacionPago | None = None, aceptadas: bool = True) -> None:
        self.cotizacion = cotizacion_ if cotizacion_ is not None else cotizacion()
        self.aceptadas = aceptadas
        self.error: Exception | None = None
        self.correlaciones: list[str] = []

    async def obtener(self, cotizacion_id, correlation_id):
        self.correlaciones.append(correlation_id)
        if self.error:
            raise self.error
        if cotizacion_id != self.cotizacion.cotizacion_id:
            raise CotizacionNoEncontradaError(str(cotizacion_id))
        return self.cotizacion

    async def condiciones_aceptadas(self, cotizacion_id, correlation_id):
        if self.error:
            raise self.error
        return self.aceptadas


class FirmasFalsas(FirmaGateway):
    def __init__(self, firma: FirmaPago | None = "por-defecto") -> None:
        if firma == "por-defecto":
            firma = FirmaPago(firma_id=uuid.uuid4(), cliente_id=CLIENTE_ID, estado="CAPTURADA")
        self.firma = firma
        self.llamadas = 0

    async def obtener_vigente(self, cotizacion_id, correlation_id):
        self.llamadas += 1
        return self.firma


class ProveedorFalso(ProveedorPago):
    """Responde, en orden, con cada resultado o excepción configurados."""

    def __init__(self, *respuestas) -> None:
        self.respuestas = list(respuestas) or [ResultadoCobro(aprobado=True, referencia="PP-1")]
        self.solicitudes: list[SolicitudCobro] = []

    async def cobrar(self, solicitud):
        self.solicitudes.append(solicitud)
        respuesta = self.respuestas.pop(0) if len(self.respuestas) > 1 else self.respuestas[0]
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta


class ProveedorTarjetaFalso(ProveedorFalso, ProveedorTarjeta):
    def __init__(self, *respuestas) -> None:
        super().__init__(*respuestas)
        self.tokenizaciones: list[tuple[DatosTarjeta, str]] = []
        self.error_tokenizacion: Exception | None = None

    async def tokenizar(self, tarjeta: DatosTarjeta, correlation_id: str) -> str:
        self.tokenizaciones.append((tarjeta, correlation_id))
        if self.error_tokenizacion:
            raise self.error_tokenizacion
        marca = {"3": "AMEX", "4": "VISA", "5": "MASTERCARD"}.get(
            tarjeta.numero_tarjeta[0], "CARD"
        )
        return f"tok_{marca}_{tarjeta.numero_tarjeta[-4:]}"


class Transaccion:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1
