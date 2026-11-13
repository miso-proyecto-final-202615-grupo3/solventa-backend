import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from src.application.ports.cotizaciones import (
    CondicionesEmision,
    CotizacionEmision,
    CotizacionGateway,
    ProductoEmision,
)
from src.application.ports.titulares import Titular, TitularGateway
from src.domain.eventos.entities import EventoOutbox
from src.domain.eventos.mensajes import TIPO_POLIZA_EMITIDA, PagoAprobado, payload_poliza_emitida
from src.domain.eventos.repositories import EventoOutboxRepository
from src.domain.firmas.repositories import FirmaDigitalRepository
from src.domain.polizas.entities import (
    ESTADO_POLIZA_EMITIDA,
    ContratoPoliza,
    EstadoCertificado,
    Poliza,
    PolizaCobertura,
)
from src.domain.polizas.repositories import PolizaDuplicadaError, PolizaRepository

logger = logging.getLogger(__name__)

_CENTAVOS = Decimal("0.01")


class FirmaRequeridaError(Exception):
    """La cotización no tiene una firma digital vigente del cliente que pagó."""


class PagoInconsistenteError(Exception):
    """El pago aprobado no corresponde a la cotización (otro cliente u otro importe)."""


class DatosEmisionInvalidosError(Exception):
    """La cotización o sus condiciones no traen lo necesario para emitir la póliza."""


@dataclass(frozen=True)
class ResultadoEmision:
    poliza: Poliza
    creada: bool


def numero_de_poliza(emitida_en: datetime) -> str:
    return f"POL-{emitida_en:%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"


def _fecha_con_zona(valor: Any) -> datetime:
    try:
        fecha = datetime.fromisoformat(str(valor))
    except ValueError as exc:
        raise DatosEmisionInvalidosError(f"Fecha de vigencia inválida: {valor!r}.") from exc
    return fecha if fecha.tzinfo is not None else fecha.replace(tzinfo=UTC)


def _vigencia(condiciones: CondicionesEmision) -> tuple[datetime, datetime]:
    """Vigencia aceptada por el cliente en las condiciones particulares de la cotización."""
    propuesta = condiciones.condiciones_particulares.get("vigencia_propuesta")
    if not isinstance(propuesta, dict) or not propuesta.get("desde") or not propuesta.get("hasta"):
        raise DatosEmisionInvalidosError("Las condiciones no traen la vigencia propuesta.")
    desde, hasta = _fecha_con_zona(propuesta["desde"]), _fecha_con_zona(propuesta["hasta"])
    if hasta <= desde:
        raise DatosEmisionInvalidosError("La vigencia propuesta termina antes de comenzar.")
    return desde, hasta


def _datos_contrato(
    cotizacion: CotizacionEmision,
    producto: ProductoEmision,
    condiciones: CondicionesEmision,
    titular: Titular,
) -> dict[str, Any]:
    return {
        "moneda": cotizacion.moneda,
        "titular": {
            "nombre": titular.nombre_completo,
            "tipo_documento": titular.tipo_documento,
            "numero_identificacion": titular.numero_identificacion,
        },
        "producto": {"codigo": producto.codigo, "nombre": producto.nombre, "ramo": producto.ramo},
        "coberturas": [
            {
                "cobertura_id": str(c.cobertura_id),
                "codigo": c.codigo,
                "nombre": c.nombre,
                "limite_asegurado": str(c.limite_asegurado),
                "deducible": str(c.deducible),
                "prima": str(c.prima),
            }
            for c in cotizacion.coberturas
        ],
        "prima": {
            "base": str(cotizacion.prima_base),
            "neta": str(cotizacion.prima_neta),
            "impuestos": [
                {"concepto": i.concepto, "tasa": str(i.tasa), "valor": str(i.valor)}
                for i in cotizacion.impuestos
            ],
            "total": str(cotizacion.prima_total),
        },
        "condiciones": {
            "version_generales": condiciones.version_condiciones_generales,
            "aceptadas_en": condiciones.aceptadas_en.isoformat()
            if condiciones.aceptadas_en
            else None,
            "particulares": condiciones.condiciones_particulares,
        },
    }


class EmitirPolizaUseCase:
    """Emite la póliza de una cotización cuya prima inicial ya fue pagada (HU1.3.6).

    Es idempotente: SQS entrega los mensajes al menos una vez, y el índice único de
    poliza.cotizacion_id impide que dos entregas simultáneas emitan dos pólizas.
    """

    def __init__(
        self,
        polizas: PolizaRepository,
        firmas: FirmaDigitalRepository,
        eventos: EventoOutboxRepository,
        cotizaciones: CotizacionGateway,
        titulares: TitularGateway,
        commit: Callable[[], Awaitable[None]],
        rollback: Callable[[], Awaitable[None]],
        ahora: Callable[[], datetime] = lambda: datetime.now(UTC),
        generar_numero: Callable[[datetime], str] = numero_de_poliza,
    ) -> None:
        self.polizas = polizas
        self.firmas = firmas
        self.eventos = eventos
        self.cotizaciones = cotizaciones
        self.titulares = titulares
        self._commit = commit
        self._rollback = rollback
        self._ahora = ahora
        self._generar_numero = generar_numero

    async def ejecutar(self, pago: PagoAprobado, correlation_id: str) -> ResultadoEmision:
        existente = await self.polizas.obtener_por_cotizacion(pago.cotizacion_id)
        if existente is not None:
            return ResultadoEmision(poliza=existente, creada=False)

        firma = await self.firmas.obtener_activa_por_cotizacion(pago.cotizacion_id)
        if firma is None or firma.cliente_id != pago.cliente_id:
            raise FirmaRequeridaError("La cotización no tiene una firma digital del cliente.")

        cotizacion = await self.cotizaciones.obtener_cotizacion(pago.cotizacion_id, correlation_id)
        self._validar_pago(pago, cotizacion)
        producto = await self.cotizaciones.obtener_producto(cotizacion.producto_codigo, correlation_id)
        condiciones = await self.cotizaciones.obtener_condiciones(pago.cotizacion_id, correlation_id)
        titular = await self.titulares.obtener(pago.cliente_id, correlation_id)
        if not cotizacion.coberturas:
            raise DatosEmisionInvalidosError("La cotización no tiene coberturas.")
        vigencia_desde, vigencia_hasta = _vigencia(condiciones)

        emitida_en = self._ahora()
        poliza = Poliza(
            cliente_id=pago.cliente_id,
            cotizacion_id=pago.cotizacion_id,
            producto_id=producto.producto_id,
            numero=self._generar_numero(emitida_en),
            estado=ESTADO_POLIZA_EMITIDA,
            vigencia_desde=vigencia_desde,
            vigencia_hasta=vigencia_hasta,
            emitida_en=emitida_en,
            ramo=producto.ramo,
            titular_nombre=titular.nombre_completo,
            estado_certificado=EstadoCertificado.PENDIENTE,
        )
        poliza.coberturas = [
            PolizaCobertura(
                poliza_id=poliza.poliza_id,
                cobertura_id=c.cobertura_id,
                limite_asegurado=c.limite_asegurado,
                deducible=c.deducible,
                prima=c.prima,
            )
            for c in cotizacion.coberturas
        ]
        contrato = ContratoPoliza(
            poliza_id=poliza.poliza_id,
            datos=_datos_contrato(cotizacion, producto, condiciones, titular),
        )

        try:
            await self.polizas.guardar(poliza)
            await self.polizas.guardar_contrato(contrato)
            if not await self.firmas.vincular_a_poliza(firma.firma_id, poliza.poliza_id):
                raise FirmaRequeridaError("La firma de la cotización cambió durante la emisión.")
            await self.eventos.agregar(self._evento_poliza_emitida(poliza, cotizacion, correlation_id))
            await self._commit()
        except PolizaDuplicadaError:
            # Otra entrega del mismo mensaje ganó la carrera: su póliza es la válida.
            await self._rollback()
            existente = await self.polizas.obtener_por_cotizacion(pago.cotizacion_id)
            if existente is None:
                raise
            return ResultadoEmision(poliza=existente, creada=False)
        except Exception:
            await self._rollback()
            raise
        logger.info(
            "Póliza %s emitida para la cotización %s (correlation_id=%s).",
            poliza.numero,
            poliza.cotizacion_id,
            correlation_id,
        )
        return ResultadoEmision(poliza=poliza, creada=True)

    @staticmethod
    def _validar_pago(pago: PagoAprobado, cotizacion: CotizacionEmision) -> None:
        if cotizacion.cliente_id != pago.cliente_id:
            raise PagoInconsistenteError("La cotización pertenece a otro cliente.")
        esperado = cotizacion.prima_total.quantize(_CENTAVOS, rounding=ROUND_HALF_UP)
        if pago.monto.quantize(_CENTAVOS, rounding=ROUND_HALF_UP) != esperado:
            raise PagoInconsistenteError(
                f"El pago ({pago.monto}) no coincide con la prima de la cotización ({esperado})."
            )
        if pago.moneda != cotizacion.moneda:
            raise PagoInconsistenteError("La moneda del pago no coincide con la de la cotización.")

    def _evento_poliza_emitida(
        self, poliza: Poliza, cotizacion: CotizacionEmision, correlation_id: str
    ) -> EventoOutbox:
        evento_id = uuid.uuid4()
        creado_en = self._ahora()
        return EventoOutbox(
            evento_id=evento_id,
            tipo=TIPO_POLIZA_EMITIDA,
            agregado_id=poliza.poliza_id,
            creado_en=creado_en,
            payload=payload_poliza_emitida(
                evento_id,
                creado_en,
                correlation_id,
                poliza_id=poliza.poliza_id,
                cliente_id=poliza.cliente_id,
                cotizacion_id=poliza.cotizacion_id,
                producto_id=poliza.producto_id,
                numero=poliza.numero,
                vigencia_desde=poliza.vigencia_desde,
                vigencia_hasta=poliza.vigencia_hasta,
                prima_total=poliza.prima_total,
                moneda=cotizacion.moneda,
            ),
        )
