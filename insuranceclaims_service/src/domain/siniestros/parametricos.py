"""Dominio de los siniestros paramétricos (HU4.2.3).

Un evento externo (clima, vuelos) se normaliza a un índice + una medida. Cada póliza suscrita a ese índice
tiene su propio umbral; si la medida lo alcanza, la póliza se activa y se paga la compensación pactada
(sin demostrar pérdida). Las reglas siguen el patrón Strategy: una por cobertura.
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol

from src.domain.siniestros.errores import ErrorSiniestro

# Producto del Motor de Cotización al que aplican las coberturas paramétricas.
PRODUCTO_PARAMETRICO = "SEGURO_PARAMETRICO"
_NAMESPACE_COBERTURAS = uuid.UUID("6f1c2a8e-3b7d-4c55-9a0e-2d4b6f8a1c3e")


class TipoEvento(str, Enum):
    LLUVIA = "LLUVIA"
    RETRASO_VUELO = "RETRASO_VUELO"


class CoberturaParametrica(str, Enum):
    LLUVIA_EXTREMA = "LLUVIA_EXTREMA"
    RETRASO_VUELO = "RETRASO_VUELO"


class EstadoEvento(str, Enum):
    ENCOLADO = "ENCOLADO"  # confirmado por SQS, aún no consumido (no se guarda en la tabla)
    RECIBIDO = "RECIBIDO"
    PROCESADO = "PROCESADO"
    DESCARTADO = "DESCARTADO"
    FALLIDO = "FALLIDO"


class ResultadoPoliza(str, Enum):
    ACTIVADA = "ACTIVADA"
    BAJO_UMBRAL = "BAJO_UMBRAL"
    POLIZA_NO_VIGENTE = "POLIZA_NO_VIGENTE"


class EventoNoProcesable(ErrorSiniestro):
    """El evento no se puede interpretar: no se reintenta (queda DESCARTADO, la "DLQ" del diseño)."""

    status_code = 422
    codigo = "EVENTO_NO_PROCESABLE"
    mensaje = "El evento no se puede procesar."


def cobertura_id(cobertura: str) -> uuid.UUID:
    """UUID estable de la cobertura: el catálogo de coberturas vive en el Motor de Cotización."""
    return uuid.uuid5(_NAMESPACE_COBERTURAS, cobertura)


def normalizar_indice(valor: str) -> str:
    return "".join(valor.split()).upper()


@dataclass(frozen=True)
class EventoNormalizado:
    tipo: TipoEvento
    cobertura: CoberturaParametrica
    indice: str
    medida: str
    valor: Decimal
    unidad: str
    ocurrido_en: datetime


@dataclass
class PolizaParametrica:
    poliza_id: uuid.UUID
    cliente_id: uuid.UUID
    poliza_numero: str
    cobertura: str
    indice: str
    umbral: Decimal
    monto_compensacion: Decimal
    moneda: str
    actualizada_en: datetime
    activa: bool = True
    poliza_parametrica_id: uuid.UUID = field(default_factory=uuid.uuid4)


class ReglaParametrica(Protocol):
    cobertura: CoberturaParametrica
    tipo_evento: TipoEvento

    def normalizar(self, datos: dict, ocurrido_en: datetime) -> EventoNormalizado: ...

    def cumple(self, evento: EventoNormalizado, poliza: PolizaParametrica) -> bool: ...

    def describir(self, evento: EventoNormalizado, poliza: PolizaParametrica) -> str: ...


def _decimal(datos: dict, campo: str) -> Decimal:
    valor = datos.get(campo)
    if isinstance(valor, bool) or not isinstance(valor, int | float | str):
        raise EventoNoProcesable(f"falta {campo}")
    try:
        numero = Decimal(str(valor))
    except ArithmeticError as exc:
        raise EventoNoProcesable(f"{campo} no es numérico") from exc
    if not numero.is_finite() or numero < 0:
        raise EventoNoProcesable(f"{campo} fuera de rango")
    return numero


def _texto(datos: dict, campo: str) -> str:
    valor = datos.get(campo)
    if not isinstance(valor, str) or not normalizar_indice(valor):
        raise EventoNoProcesable(f"falta {campo}")
    return normalizar_indice(valor)


class _ReglaUmbral:
    """Regla "la medida alcanza el umbral de la póliza" sobre un índice (zona o vuelo)."""

    cobertura: CoberturaParametrica
    tipo_evento: TipoEvento
    campo_indice: str
    medida: str
    unidad: str
    texto: str

    def normalizar(self, datos: dict, ocurrido_en: datetime) -> EventoNormalizado:
        return EventoNormalizado(
            tipo=self.tipo_evento, cobertura=self.cobertura, indice=_texto(datos, self.campo_indice),
            medida=self.medida, valor=_decimal(datos, self.medida), unidad=self.unidad, ocurrido_en=ocurrido_en,
        )

    def cumple(self, evento: EventoNormalizado, poliza: PolizaParametrica) -> bool:
        return evento.indice == poliza.indice and evento.valor >= poliza.umbral

    def describir(self, evento: EventoNormalizado, poliza: PolizaParametrica) -> str:
        return (
            f"{self.cobertura.value}: {self.medida}={evento.valor} {self.unidad} en {evento.indice} "
            f">= umbral {poliza.umbral} {self.unidad}"
        )

    def resumen(self, evento: EventoNormalizado, poliza: PolizaParametrica) -> str:
        return self.texto.format(valor=_bonito(evento.valor), indice=evento.indice, umbral=_bonito(poliza.umbral))


class ReglaLluviaExtrema(_ReglaUmbral):
    cobertura = CoberturaParametrica.LLUVIA_EXTREMA
    tipo_evento = TipoEvento.LLUVIA
    campo_indice = "zona"
    medida = "precipitacion_mm"
    unidad = "mm"
    texto = "Siniestro automático: lluvia de {valor} mm en {indice} (umbral {umbral} mm)."


class ReglaRetrasoVuelo(_ReglaUmbral):
    cobertura = CoberturaParametrica.RETRASO_VUELO
    tipo_evento = TipoEvento.RETRASO_VUELO
    campo_indice = "vuelo"
    medida = "retraso_minutos"
    unidad = "min"
    texto = "Siniestro automático: el vuelo {indice} se retrasó {valor} min (umbral {umbral} min)."


def _bonito(valor: Decimal) -> str:
    return format(valor.normalize(), "f") if valor == valor.to_integral() else format(valor, "f")


REGLAS: dict[TipoEvento, _ReglaUmbral] = {regla.tipo_evento: regla for regla in (ReglaLluviaExtrema(), ReglaRetrasoVuelo())}
UMBRAL_POR_DEFECTO = {CoberturaParametrica.LLUVIA_EXTREMA: Decimal("50"), CoberturaParametrica.RETRASO_VUELO: Decimal("120")}


def regla_para(tipo: str) -> _ReglaUmbral:
    try:
        return REGLAS[TipoEvento(tipo)]
    except ValueError as exc:
        raise EventoNoProcesable(f"tipo de evento desconocido: {tipo}") from exc
