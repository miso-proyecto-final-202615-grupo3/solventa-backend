import hashlib
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from src.application.ports.cotizaciones import (
    CotizacionGateway,
    CotizacionNoEncontradaError,
    CotizacionPago,
)
from src.application.ports.firmas import FirmaGateway
from src.application.ports.proveedor_pago import (
    DatosTarjeta,
    ProveedorPago,
    ProveedorPagoError,
    ProveedorTarjeta,
    SolicitudCobro,
    SolicitudInvalidaError,
)
from src.domain.eventos.entities import TIPO_PAGO_APROBADO, EventoOutbox
from src.domain.eventos.repositories import EventoOutboxRepository
from src.domain.pagos.entities import EstadoPago, MetodoPago, PagoPrima
from src.domain.pagos.repositories import PagoDuplicadoError, PagoPrimaRepository

logger = logging.getLogger(__name__)

COTIZACION_VIGENTE = "VIGENTE"
CODIGO_SOLICITUD_INVALIDA = "SOLICITUD_INVALIDA"


class CotizacionNoVigenteError(Exception):
    pass


class CondicionesNoAceptadasError(Exception):
    pass


class FirmaRequeridaError(Exception):
    pass


class PagoEnCursoError(Exception):
    pass


class PagoYaAprobadoError(Exception):
    pass


class IdempotencyKeyReutilizadaError(Exception):
    pass


class PagoNoEncontradoError(Exception):
    pass


@dataclass(frozen=True)
class SolicitudPago:
    cotizacion_id: uuid.UUID
    cliente_id: uuid.UUID
    metodo_pago: MetodoPago
    credencial: str = field(repr=False)
    tarjeta: DatosTarjeta | None = field(default=None, repr=False)


@dataclass(frozen=True)
class ResultadoPago:
    pago: PagoPrima
    creado: bool


def _hash_solicitud(solicitud: SolicitudPago) -> str:
    campos = (
        str(solicitud.cotizacion_id),
        str(solicitud.cliente_id),
        solicitud.metodo_pago.value,
        solicitud.credencial,
    )
    return hashlib.sha256("|".join(campos).encode("utf-8")).hexdigest()


class ProcesarPagoPrimaUseCase:
    def __init__(
        self,
        pagos: PagoPrimaRepository,
        eventos: EventoOutboxRepository,
        cotizaciones: CotizacionGateway,
        firmas: FirmaGateway,
        proveedores: dict[MetodoPago, ProveedorPago],
        proveedor_nombre: str,
        commit: Callable[[], Awaitable[None]],
        rollback: Callable[[], Awaitable[None]],
        requiere_firma: bool,
        pendiente_ttl: timedelta,
        ahora: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.pagos = pagos
        self.eventos = eventos
        self.cotizaciones = cotizaciones
        self.firmas = firmas
        self.proveedores = proveedores
        self.proveedor_nombre = proveedor_nombre
        self._commit = commit
        self._rollback = rollback
        self.requiere_firma = requiere_firma
        self.pendiente_ttl = pendiente_ttl
        self._ahora = ahora

    async def ejecutar(
        self, solicitud: SolicitudPago, idempotency_key: str, correlation_id: str
    ) -> ResultadoPago:
        existente = await self.pagos.obtener_por_idempotency_key(
            solicitud.cliente_id, idempotency_key
        )
        if existente is not None:
            if (
                existente.cotizacion_id != solicitud.cotizacion_id
                or existente.metodo_pago != solicitud.metodo_pago
            ):
                raise IdempotencyKeyReutilizadaError(
                    "La clave de idempotencia ya se usó con otra solicitud de pago."
                )
            solicitud = await self._tokenizar_tarjeta(solicitud, correlation_id)
            return await self._repetir(
                existente, _hash_solicitud(solicitud), solicitud, correlation_id
            )

        cotizacion = await self._validar_precondiciones(solicitud, correlation_id)
        await self._validar_sin_pago_activo(solicitud.cotizacion_id)
        solicitud = await self._tokenizar_tarjeta(solicitud, correlation_id)
        huella = _hash_solicitud(solicitud)

        ahora = self._ahora()
        pago = PagoPrima(
            cotizacion_id=solicitud.cotizacion_id,
            cliente_id=solicitud.cliente_id,
            monto=cotizacion.prima_total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            moneda=cotizacion.moneda,
            metodo_pago=solicitud.metodo_pago,
            proveedor=self.proveedor_nombre,
            idempotency_key=idempotency_key,
            hash_solicitud=huella,
            correlation_id=correlation_id,
            creado_en=ahora,
            actualizado_en=ahora,
        )
        try:
            await self.pagos.crear(pago)
            await self._commit()
        except PagoDuplicadoError:
            # Otro request ganó la carrera: la misma clave devuelve su pago; si no, hay un pago activo.
            await self._rollback()
            existente = await self.pagos.obtener_por_idempotency_key(
                solicitud.cliente_id, idempotency_key
            )
            if existente is not None:
                return await self._repetir(existente, huella, solicitud, correlation_id)
            await self._validar_sin_pago_activo(solicitud.cotizacion_id)
            raise PagoEnCursoError("Hay un pago de la cotización en curso.") from None
        return await self._cobrar(pago, solicitud, correlation_id)

    async def _tokenizar_tarjeta(
        self, solicitud: SolicitudPago, correlation_id: str
    ) -> SolicitudPago:
        if solicitud.metodo_pago != MetodoPago.TARJETA_CREDITO:
            return solicitud
        proveedor = self.proveedores[MetodoPago.TARJETA_CREDITO]
        if not isinstance(proveedor, ProveedorTarjeta) or solicitud.tarjeta is None:
            raise ProveedorPagoError("CONFIGURACION_INVALIDA")
        token = await proveedor.tokenizar(solicitud.tarjeta, correlation_id)
        return replace(solicitud, credencial=token, tarjeta=None)

    async def _validar_precondiciones(
        self, solicitud: SolicitudPago, correlation_id: str
    ) -> CotizacionPago:
        cotizacion = await self.cotizaciones.obtener(solicitud.cotizacion_id, correlation_id)
        # Una cotización ajena se informa como inexistente para no revelar su existencia.
        if cotizacion.cliente_id != solicitud.cliente_id:
            raise CotizacionNoEncontradaError(str(solicitud.cotizacion_id))
        if cotizacion.estado != COTIZACION_VIGENTE or cotizacion.expira_en <= self._ahora():
            raise CotizacionNoVigenteError("La cotización no está vigente.")
        if not await self.cotizaciones.condiciones_aceptadas(
            solicitud.cotizacion_id, correlation_id
        ):
            raise CondicionesNoAceptadasError("Las condiciones no han sido aceptadas.")
        if self.requiere_firma:
            firma = await self.firmas.obtener_vigente(solicitud.cotizacion_id, correlation_id)
            if firma is None or firma.cliente_id != solicitud.cliente_id:
                raise FirmaRequeridaError("La cotización no tiene una firma digital vigente.")
        return cotizacion

    async def _validar_sin_pago_activo(self, cotizacion_id: uuid.UUID) -> None:
        activo = await self.pagos.obtener_activo_por_cotizacion(cotizacion_id)
        if activo is None:
            return
        if activo.estado == EstadoPago.APROBADO:
            raise PagoYaAprobadoError("La prima de la cotización ya fue pagada.")
        raise PagoEnCursoError(
            "Hay un pago de la cotización en curso; reintente con la misma Idempotency-Key."
        )

    async def _repetir(
        self,
        existente: PagoPrima,
        huella: str,
        solicitud: SolicitudPago,
        correlation_id: str,
    ) -> ResultadoPago:
        if existente.hash_solicitud != huella:
            raise IdempotencyKeyReutilizadaError(
                "La clave de idempotencia ya se usó con otra solicitud de pago."
            )
        if existente.estado in (EstadoPago.APROBADO, EstadoPago.RECHAZADO):
            return ResultadoPago(pago=existente, creado=False)
        if (
            existente.estado == EstadoPago.PENDIENTE
            and self._ahora() - existente.actualizado_en < self.pendiente_ttl
        ):
            raise PagoEnCursoError("El pago se está procesando.")

        # ERROR o PENDIENTE abandonado: se reintenta con la misma referencia ante el proveedor,
        # que por idempotencia no cobra dos veces.
        existente.estado = EstadoPago.PENDIENTE
        existente.error_codigo = None
        existente.actualizado_en = self._ahora()
        if not await self.pagos.actualizar(existente):
            await self._rollback()
            raise PagoEnCursoError("El pago se está procesando.")
        await self._commit()
        resultado = await self._cobrar(existente, solicitud, correlation_id)
        return ResultadoPago(pago=resultado.pago, creado=False)

    async def _cobrar(
        self, pago: PagoPrima, solicitud: SolicitudPago, correlation_id: str
    ) -> ResultadoPago:
        proveedor = self.proveedores[pago.metodo_pago]
        try:
            resultado = await proveedor.cobrar(
                SolicitudCobro(
                    referencia=str(pago.pago_id),
                    monto=pago.monto,
                    moneda=pago.moneda,
                    credencial=solicitud.credencial,
                    correlation_id=correlation_id,
                )
            )
        except SolicitudInvalidaError as exc:
            pago.estado = EstadoPago.RECHAZADO
            pago.codigo_rechazo = CODIGO_SOLICITUD_INVALIDA
            pago.error_codigo = exc.codigo
            await self._guardar_resultado(pago)
            return ResultadoPago(pago=pago, creado=True)
        except ProveedorPagoError as exc:
            await self._registrar_error(pago, exc.codigo)
            raise
        except Exception as exc:
            logger.exception("Falló el cobro de la prima %s.", pago.pago_id)
            await self._registrar_error(pago, "ERROR_INESPERADO")
            raise ProveedorPagoError("ERROR_INESPERADO", type(exc).__name__) from exc

        pago.proveedor_referencia = resultado.referencia
        pago.tarjeta_ultimos4 = resultado.tarjeta_ultimos4
        pago.tarjeta_marca = resultado.tarjeta_marca
        pago.error_codigo = None
        if resultado.aprobado:
            pago.estado = EstadoPago.APROBADO
            await self._guardar_resultado(pago, publicar=True)
        else:
            pago.estado = EstadoPago.RECHAZADO
            pago.codigo_rechazo = resultado.codigo_rechazo or "RECHAZADO_POR_PROVEEDOR"
            await self._guardar_resultado(pago)
        return ResultadoPago(pago=pago, creado=True)

    async def _guardar_resultado(self, pago: PagoPrima, publicar: bool = False) -> None:
        pago.procesado_en = self._ahora()
        pago.actualizado_en = pago.procesado_en
        if not await self.pagos.actualizar(pago):
            await self._rollback()
            raise PagoEnCursoError("El pago fue modificado concurrentemente.")
        if publicar:
            await self.eventos.agregar(self._evento_pago_aprobado(pago))
        await self._commit()

    async def _registrar_error(self, pago: PagoPrima, codigo: str) -> None:
        pago.estado = EstadoPago.ERROR
        pago.error_codigo = codigo[:60]
        pago.actualizado_en = self._ahora()
        if await self.pagos.actualizar(pago):
            await self._commit()
        else:
            await self._rollback()

    def _evento_pago_aprobado(self, pago: PagoPrima) -> EventoOutbox:
        evento_id = uuid.uuid4()
        return EventoOutbox(
            evento_id=evento_id,
            tipo=TIPO_PAGO_APROBADO,
            agregado_id=pago.pago_id,
            creado_en=self._ahora(),
            payload={
                "evento_id": str(evento_id),
                "tipo": TIPO_PAGO_APROBADO,
                "version": 1,
                "ocurrido_en": pago.procesado_en.isoformat() if pago.procesado_en else None,
                "correlation_id": pago.correlation_id,
                "datos": {
                    "pago_id": str(pago.pago_id),
                    "cotizacion_id": str(pago.cotizacion_id),
                    "cliente_id": str(pago.cliente_id),
                    "monto": str(pago.monto),
                    "moneda": pago.moneda,
                    "metodo_pago": pago.metodo_pago.value,
                    "proveedor_referencia": pago.proveedor_referencia,
                },
            },
        )
