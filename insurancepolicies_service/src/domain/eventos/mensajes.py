"""Contratos de los mensajes SQS que consume y produce el servicio.

PagoAprobado lo publica payments_service; este módulo solo lo lee. PolizaEmitida lo publica este
servicio, a través de su outbox, y lo consume el generador de certificados.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

TIPO_PAGO_APROBADO = "PagoAprobado"
TIPO_POLIZA_EMITIDA = "PolizaEmitida"
VERSION_MENSAJE = 1


class MensajeInvalidoError(Exception):
    """El mensaje no cumple el contrato: reintentarlo no lo arregla."""


def _datos(payload: Any, tipo: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise MensajeInvalidoError("El mensaje no es un objeto JSON.")
    if payload.get("tipo") != tipo:
        raise MensajeInvalidoError(f"El mensaje no es de tipo {tipo}.")
    if payload.get("version") != VERSION_MENSAJE:
        raise MensajeInvalidoError(f"Versión de {tipo} no soportada: {payload.get('version')!r}.")
    datos = payload.get("datos")
    if not isinstance(datos, dict):
        raise MensajeInvalidoError(f"{tipo} no trae el bloque 'datos'.")
    return datos


def _uuid(datos: dict[str, Any], campo: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(datos[campo]))
    except (KeyError, ValueError) as exc:
        raise MensajeInvalidoError(f"El campo '{campo}' no es un UUID válido.") from exc


@dataclass(frozen=True)
class PagoAprobado:
    evento_id: str
    pago_id: uuid.UUID
    cotizacion_id: uuid.UUID
    cliente_id: uuid.UUID
    monto: Decimal
    moneda: str
    metodo_pago: str
    proveedor_referencia: str | None
    correlation_id: str | None

    @classmethod
    def desde_payload(cls, payload: Any) -> "PagoAprobado":
        datos = _datos(payload, TIPO_PAGO_APROBADO)
        try:
            monto = Decimal(str(datos["monto"]))
            if not monto.is_finite() or monto <= 0:
                raise InvalidOperation
        except (KeyError, InvalidOperation) as exc:
            raise MensajeInvalidoError("El campo 'monto' no es un importe válido.") from exc
        moneda = datos.get("moneda")
        if not isinstance(moneda, str) or len(moneda) != 3:
            raise MensajeInvalidoError("El campo 'moneda' no es válido.")
        correlation_id = payload.get("correlation_id")
        return cls(
            evento_id=str(payload.get("evento_id") or ""),
            pago_id=_uuid(datos, "pago_id"),
            cotizacion_id=_uuid(datos, "cotizacion_id"),
            cliente_id=_uuid(datos, "cliente_id"),
            monto=monto,
            moneda=moneda,
            metodo_pago=str(datos.get("metodo_pago") or ""),
            proveedor_referencia=datos.get("proveedor_referencia"),
            correlation_id=correlation_id if isinstance(correlation_id, str) else None,
        )


@dataclass(frozen=True)
class PolizaEmitida:
    evento_id: str
    poliza_id: uuid.UUID
    cliente_id: uuid.UUID
    cotizacion_id: uuid.UUID
    numero: str
    correlation_id: str | None

    @classmethod
    def desde_payload(cls, payload: Any) -> "PolizaEmitida":
        datos = _datos(payload, TIPO_POLIZA_EMITIDA)
        correlation_id = payload.get("correlation_id")
        return cls(
            evento_id=str(payload.get("evento_id") or ""),
            poliza_id=_uuid(datos, "poliza_id"),
            cliente_id=_uuid(datos, "cliente_id"),
            cotizacion_id=_uuid(datos, "cotizacion_id"),
            numero=str(datos.get("numero") or ""),
            correlation_id=correlation_id if isinstance(correlation_id, str) else None,
        )


def payload_poliza_emitida(
    evento_id: uuid.UUID,
    ocurrido_en: datetime,
    correlation_id: str,
    *,
    poliza_id: uuid.UUID,
    cliente_id: uuid.UUID,
    cotizacion_id: uuid.UUID,
    producto_id: uuid.UUID,
    numero: str,
    vigencia_desde: datetime,
    vigencia_hasta: datetime,
    prima_total: Decimal,
    moneda: str,
) -> dict[str, Any]:
    return {
        "evento_id": str(evento_id),
        "tipo": TIPO_POLIZA_EMITIDA,
        "version": VERSION_MENSAJE,
        "ocurrido_en": ocurrido_en.isoformat(),
        "correlation_id": correlation_id,
        "datos": {
            "poliza_id": str(poliza_id),
            "cliente_id": str(cliente_id),
            "cotizacion_id": str(cotizacion_id),
            "producto_id": str(producto_id),
            "numero": numero,
            "vigencia_desde": vigencia_desde.isoformat(),
            "vigencia_hasta": vigencia_hasta.isoformat(),
            "prima_total": str(prima_total),
            "moneda": moneda,
        },
    }
