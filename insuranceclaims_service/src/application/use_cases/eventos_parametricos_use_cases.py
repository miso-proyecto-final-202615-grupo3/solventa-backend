"""HU4.2.3 · Siniestros paramétricos: recibir el evento, suscribir pólizas, procesar y consultar la traza.

Ingesta y procesamiento están separados (ASR-ESC-002): la fuente recibe el ACK apenas el evento queda
guardado; el consumidor lo procesa después, con idempotencia por `event_id` y claves derivadas.
"""
import hashlib
import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.bus_eventos import BusEventosParametricos, BusNoDisponible
from src.application.ports.polizas import PolizasNoDisponibles, PolizasPort
from src.domain.siniestros.entities import (
    ActivacionParametrica,
    ActivacionPoliza,
    EventoExterno,
    EventoOutbox,
    Indemnizacion,
    Siniestro,
)
from src.domain.siniestros.enums import CanalReporte, EstadoSiniestro
from src.domain.siniestros.errores import (
    EventoEnConflicto,
    EventoNoEncontrado,
    PolizaNoEncontrada,
    PolizaNoParametrica,
    ServicioNoDisponible,
)
from src.domain.siniestros.folio import generar_numero
from src.domain.siniestros.parametricos import (
    PRODUCTO_PARAMETRICO,
    EstadoEvento,
    EventoNormalizado,
    PolizaParametrica,
    ResultadoPoliza,
    cobertura_id,
    normalizar_indice,
    regla_para,
)
from src.domain.siniestros.repositories import (
    ActivacionParametricaRepository,
    ActivacionPolizaRepository,
    EventoExternoRepository,
    EventoOutboxRepository,
    IndemnizacionRepository,
    PolizaParametricaRepository,
    SiniestroRepository,
)

logger = logging.getLogger(__name__)

TIPO_PAGO_SOLICITADO = "PAGO_INDEMNIZACION_SOLICITADO"
ESTADO_INDEMNIZACION_SOLICITADA = "PAGO_SOLICITADO"
ESTADO_INDEMNIZACION_PAGADA = "PAGADA"


def _utc(valor: datetime) -> datetime:
    return (valor if valor.tzinfo else valor.replace(tzinfo=UTC)).astimezone(UTC)


def checksum_evento(fuente: str, tipo: str, ocurrido_en: datetime, datos: dict) -> str:
    """Huella del contenido: el mismo `event_id` con otro contenido es un conflicto (P9)."""
    canonico = json.dumps(
        {"fuente": fuente, "tipo": tipo, "ocurrido_en": _utc(ocurrido_en).isoformat(), "datos": datos},
        sort_keys=True, separators=(",", ":"), default=str,
    )
    return hashlib.sha256(canonico.encode()).hexdigest()


@dataclass(frozen=True)
class EventoRecibido:
    evento: EventoExterno
    nuevo: bool


def mensaje_bus(evento: EventoExterno) -> dict:
    """Mensaje del bus: el evento tal como llegó más su huella y la hora de recepción."""
    return {
        "event_id": evento.event_id, "fuente": evento.fuente, "tipo": evento.tipo,
        "ocurrido_en": _utc(evento.ocurrido_en).isoformat(), "datos": evento.datos,
        "checksum": evento.checksum, "recibido_en": _utc(evento.recibido_en).isoformat(),
    }


def evento_desde_mensaje(mensaje: dict) -> EventoExterno:
    return EventoExterno(
        event_id=mensaje["event_id"], fuente=mensaje["fuente"], tipo=mensaje["tipo"], checksum=mensaje["checksum"],
        ocurrido_en=datetime.fromisoformat(mensaje["ocurrido_en"]), recibido_en=datetime.fromisoformat(mensaje["recibido_en"]),
        payload_referencia=f"sqs/{mensaje['event_id']}", estado=EstadoEvento.RECIBIDO.value, datos=mensaje.get("datos") or {},
    )


class RecibirEventoParametricoUseCase:
    def __init__(
        self,
        db: AsyncSession,
        eventos: EventoExternoRepository,
        reloj: Callable[[], datetime],
        bus: BusEventosParametricos | None = None,
    ) -> None:
        self.db, self.eventos, self.reloj, self.bus = db, eventos, reloj, bus

    async def ejecutar(
        self, event_id: str, fuente: str, tipo: str, ocurrido_en: datetime, datos: dict
    ) -> EventoRecibido:
        # Validación mínima del contrato antes de confirmar (un evento que no se entiende no entra al bus).
        regla_para(tipo).normalizar(datos, ocurrido_en)
        checksum = checksum_evento(fuente, tipo, ocurrido_en, datos)
        existente = await self.eventos.obtener_por_event_id(event_id)
        if existente is not None:
            return self._repetido(existente, checksum)
        evento = EventoExterno(
            event_id=event_id, fuente=fuente, tipo=tipo, checksum=checksum, ocurrido_en=_utc(ocurrido_en),
            recibido_en=self.reloj(), payload_referencia=f"evento_externo.datos/{event_id}",
            estado=EstadoEvento.RECIBIDO.value, datos=datos,
        )
        if self.bus is not None:
            # Diseño HA8: el ACK a la fuente sale después de que SQS confirma el mensaje. El consumidor lo
            # registra en `evento_externo` (idempotencia y traza) al procesarlo.
            try:
                await self.bus.publicar(mensaje_bus(evento), event_id)
            except BusNoDisponible as exc:
                raise ServicioNoDisponible() from exc
            evento.estado = EstadoEvento.ENCOLADO.value
            logger.info("evento_parametrico_encolado event_id=%s fuente=%s tipo=%s", event_id, fuente, tipo)
            return EventoRecibido(evento, nuevo=True)
        try:
            await self.eventos.guardar(evento)
            await self.db.commit()  # persistencia durable ANTES del ACK
        except IntegrityError:
            # Dos entregas simultáneas del mismo evento: gana la primera.
            await self.db.rollback()
            existente = await self.eventos.obtener_por_event_id(event_id)
            if existente is None:
                raise
            return self._repetido(existente, checksum)
        logger.info("evento_parametrico_recibido event_id=%s fuente=%s tipo=%s", event_id, fuente, tipo)
        return EventoRecibido(evento, nuevo=True)

    @staticmethod
    def _repetido(existente: EventoExterno, checksum: str) -> EventoRecibido:
        if existente.checksum != checksum:
            raise EventoEnConflicto()
        logger.info("evento_parametrico_repetido event_id=%s estado=%s", existente.event_id, existente.estado)
        return EventoRecibido(existente, nuevo=False)


class ConsultarEventoParametricoUseCase:
    def __init__(self, eventos: EventoExternoRepository) -> None:
        self.eventos = eventos

    async def ejecutar(self, event_id: str) -> EventoExterno:
        evento = await self.eventos.obtener_por_event_id(event_id)
        if evento is None:
            raise EventoNoEncontrado()
        return evento


class SuscribirPolizaParametricaUseCase:
    """Registra la zona o el vuelo asegurado de una póliza paramétrica (supuesto P3)."""

    def __init__(
        self, db: AsyncSession, repo: PolizaParametricaRepository, polizas: PolizasPort, reloj: Callable[[], datetime]
    ) -> None:
        self.db, self.repo, self.polizas, self.reloj = db, repo, polizas, reloj

    async def ejecutar(
        self, poliza_id: uuid.UUID, cliente_id: uuid.UUID, cobertura: str, indice: str,
        umbral: Decimal, monto_compensacion: Decimal, moneda: str, correlation_id: str,
    ) -> PolizaParametrica:
        try:
            poliza = await self.polizas.obtener(poliza_id, cliente_id, correlation_id)
        except PolizasNoDisponibles as exc:
            raise ServicioNoDisponible() from exc
        if poliza is None:
            raise PolizaNoEncontrada()
        if poliza.producto_codigo != PRODUCTO_PARAMETRICO:
            raise PolizaNoParametrica()
        suscripcion = PolizaParametrica(
            poliza_id=poliza_id, cliente_id=cliente_id, poliza_numero=poliza.numero, cobertura=cobertura,
            indice=normalizar_indice(indice), umbral=umbral, monto_compensacion=monto_compensacion,
            moneda=moneda, actualizada_en=self.reloj(),
        )
        await self.repo.guardar_o_actualizar(suscripcion)
        await self.db.commit()
        logger.info(
            "poliza_parametrica_suscrita poliza_id=%s cobertura=%s indice=%s", poliza_id, cobertura, suscripcion.indice
        )
        return suscripcion


@dataclass
class RepositoriosParametricos:
    eventos: EventoExternoRepository
    suscripciones: PolizaParametricaRepository
    activaciones: ActivacionParametricaRepository
    activaciones_poliza: ActivacionPolizaRepository
    siniestros: SiniestroRepository
    indemnizaciones: IndemnizacionRepository
    outbox: EventoOutboxRepository


class ProcesarEventoParametricoUseCase:
    """Evalúa un evento `RECIBIDO` y crea los siniestros automáticos de las pólizas que activa.

    Todo lo de un evento va en una transacción: si algo falla (p. ej. MS Pólizas caído) no queda nada a
    medias y el consumidor lo reintenta. Las claves de idempotencia evitan duplicados si el evento se repite.
    """

    def __init__(
        self, db: AsyncSession, repos: RepositoriosParametricos, polizas: PolizasPort,
        reloj: Callable[[], datetime], estados_elegibles: list[str],
    ) -> None:
        self.db, self.repos, self.polizas, self.reloj = db, repos, polizas, reloj
        self.estados_elegibles = set(estados_elegibles)

    async def ejecutar(self, evento: EventoExterno) -> list[dict]:
        regla = regla_para(evento.tipo)
        normal = regla.normalizar(evento.datos or {}, evento.ocurrido_en)
        ahora = self.reloj()
        resultado: list[dict] = []
        activacion: ActivacionParametrica | None = None
        for suscripcion in await self.repos.suscripciones.suscritas(normal.cobertura.value, normal.indice):
            item = {"poliza_id": str(suscripcion.poliza_id), "poliza_numero": suscripcion.poliza_numero,
                    "cobertura": suscripcion.cobertura, "umbral": str(suscripcion.umbral)}
            if not regla.cumple(normal, suscripcion):
                resultado.append({**item, "resultado": ResultadoPoliza.BAJO_UMBRAL.value})
                continue
            poliza = await self.polizas.obtener(suscripcion.poliza_id, suscripcion.cliente_id, evento.event_id)
            ocurrido = _utc(normal.ocurrido_en).date()
            if (
                poliza is None
                or poliza.estado not in self.estados_elegibles
                or not (poliza.vigencia_desde <= ocurrido <= poliza.vigencia_hasta)
            ):
                resultado.append({**item, "resultado": ResultadoPoliza.POLIZA_NO_VIGENTE.value})
                continue
            if activacion is None:
                activacion = await self._activacion(evento, normal, regla.describir(normal, suscripcion), ahora)
            siniestro, indemnizacion = await self._siniestro(
                evento, normal, activacion, suscripcion, poliza.producto_codigo, regla.resumen(normal, suscripcion), ahora
            )
            resultado.append({
                **item, "resultado": ResultadoPoliza.ACTIVADA.value, "siniestro_id": str(siniestro.siniestro_id),
                "numero": siniestro.numero, "monto": str(indemnizacion.monto_aprobado), "moneda": indemnizacion.moneda,
            })
        evento.estado = EstadoEvento.PROCESADO.value
        evento.resultado = resultado
        evento.procesado_en = ahora
        evento.ultimo_error = None
        await self.repos.eventos.actualizar(evento)
        await self.db.commit()
        activadas = sum(1 for r in resultado if r["resultado"] == ResultadoPoliza.ACTIVADA.value)
        logger.info(
            "evento_parametrico_procesado event_id=%s cobertura=%s indice=%s suscritas=%s activadas=%s",
            evento.event_id, normal.cobertura.value, normal.indice, len(resultado), activadas,
        )
        return resultado

    async def _activacion(
        self, evento: EventoExterno, normal: EventoNormalizado, regla_aplicada: str, ahora: datetime
    ) -> ActivacionParametrica:
        clave = f"PARAM:{evento.event_id}:{normal.cobertura.value}"
        existente = await self.repos.activaciones.obtener_por_clave(clave)
        if existente is not None:
            return existente
        activacion = ActivacionParametrica(
            evento_externo_id=evento.evento_externo_id, cobertura_id=cobertura_id(normal.cobertura.value),
            regla_aplicada=regla_aplicada[:255], estado="ACTIVADA", clave_idempotencia=clave, activada_en=ahora,
        )
        await self.repos.activaciones.guardar(activacion)
        return activacion

    async def _siniestro(
        self, evento: EventoExterno, normal: EventoNormalizado, activacion: ActivacionParametrica,
        suscripcion: PolizaParametrica, producto_codigo: str, descripcion: str, ahora: datetime,
    ) -> tuple[Siniestro, Indemnizacion]:
        clave = f"{activacion.clave_idempotencia}:{suscripcion.poliza_id}"
        existente = await self.repos.siniestros.obtener_por_clave_idempotencia(clave)
        if existente is not None:
            indemnizacion = await self.repos.indemnizaciones.obtener_de_siniestro(existente.siniestro_id)
            return existente, indemnizacion
        await self.repos.activaciones_poliza.guardar(ActivacionPoliza(
            activacion_id=activacion.activacion_id, poliza_id=suscripcion.poliza_id, estado="ACTIVADA",
            clave_idempotencia=clave, identificada_en=ahora,
        ))
        siniestro = Siniestro(
            poliza_id=suscripcion.poliza_id, tipo=normal.cobertura.value, estado=EstadoSiniestro.APROBADO.value,
            clave_idempotencia=clave, ocurrido_en=_utc(normal.ocurrido_en), reportado_en=ahora,
            activacion_id=activacion.activacion_id, cliente_id=suscripcion.cliente_id,
            canal=CanalReporte.PARAMETRICO.value, descripcion=descripcion[:500],
            poliza_numero=suscripcion.poliza_numero, producto_codigo=producto_codigo, estado_actualizado_en=ahora,
        )
        siniestro.numero = generar_numero(siniestro.siniestro_id, ahora)
        await self.repos.siniestros.guardar(siniestro)
        indemnizacion = Indemnizacion(
            siniestro_id=siniestro.siniestro_id, monto_aprobado=suscripcion.monto_compensacion,
            moneda=suscripcion.moneda, estado=ESTADO_INDEMNIZACION_SOLICITADA, aprobada_en=ahora,
        )
        await self.repos.indemnizaciones.guardar(indemnizacion)
        await self.repos.outbox.guardar(EventoOutbox(
            tipo="SINIESTRO_ESTADO", agregado_id=siniestro.siniestro_id, creado_en=ahora,
            payload={"tipo": "SINIESTRO_ESTADO", "siniestro_id": str(siniestro.siniestro_id),
                     "numero": siniestro.numero, "estado": siniestro.estado, "canal": siniestro.canal},
        ))
        await self.repos.outbox.guardar(EventoOutbox(
            tipo=TIPO_PAGO_SOLICITADO, agregado_id=siniestro.siniestro_id, creado_en=ahora,
            payload={
                "tipo": TIPO_PAGO_SOLICITADO, "indemnizacion_id": str(indemnizacion.indemnizacion_id),
                "siniestro_id": str(siniestro.siniestro_id), "numero": siniestro.numero,
                "poliza_id": str(siniestro.poliza_id), "cliente_id": str(siniestro.cliente_id),
                "monto": str(indemnizacion.monto_aprobado), "moneda": indemnizacion.moneda,
                "clave_idempotencia": f"PAGO:{clave}",
            },
        ))
        logger.info(
            "siniestro_parametrico_creado event_id=%s numero=%s poliza_id=%s monto=%s",
            evento.event_id, siniestro.numero, siniestro.poliza_id, indemnizacion.monto_aprobado,
        )
        return siniestro, indemnizacion
