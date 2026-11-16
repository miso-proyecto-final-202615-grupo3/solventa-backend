"""Datos que alimentan la plantilla del certificado.

Son solo valores crudos y serializables a JSON (importes como texto, fechas ISO sin hora): el
formato de presentación lo aplica la plantilla. La imagen de la firma no va aquí; se incrusta al
renderizar, y aquí solo quedan sus referencias.
"""
from datetime import datetime, tzinfo
from typing import Any

from src.domain.firmas.entities import FirmaDigital
from src.domain.polizas.entities import ContratoPoliza, Poliza


def _fecha(valor: datetime, zona_horaria: tzinfo) -> str:
    return valor.astimezone(zona_horaria).date().isoformat()


def _fecha_opcional(valor: str | None, zona_horaria: tzinfo) -> str | None:
    if not valor:
        return None
    try:
        return _fecha(datetime.fromisoformat(valor), zona_horaria)
    except ValueError:
        return None


def construir_datos_certificado(
    poliza: Poliza,
    contrato: ContratoPoliza,
    firma: FirmaDigital,
    zona_horaria: tzinfo,
    generado_en: datetime,
) -> dict[str, Any]:
    datos = contrato.datos
    condiciones = datos.get("condiciones", {})
    return {
        "poliza": {
            "poliza_id": str(poliza.poliza_id),
            "numero": poliza.numero,
            "estado": poliza.estado,
            "ramo": poliza.ramo,
            "emitida_en": _fecha(poliza.emitida_en, zona_horaria) if poliza.emitida_en else None,
            "vigencia_desde": _fecha(poliza.vigencia_desde, zona_horaria),
            "vigencia_hasta": _fecha(poliza.vigencia_hasta, zona_horaria),
        },
        "titular": datos.get("titular", {}),
        "producto": datos.get("producto", {}),
        "moneda": datos.get("moneda"),
        "coberturas": datos.get("coberturas", []),
        "prima": datos.get("prima", {}),
        "condiciones": {
            "version_generales": condiciones.get("version_generales"),
            "aceptadas_en": _fecha_opcional(condiciones.get("aceptadas_en"), zona_horaria),
        },
        "firma": {
            "firma_id": str(firma.firma_id),
            "capturada_en": _fecha(firma.capturada_en, zona_horaria),
            "proveedor": firma.proveedor_firma,
            "firma_hash": firma.firma_hash,
            "fingerprint_contrato": firma.fingerprint_contrato,
        },
        "generado_en": _fecha(generado_en, zona_horaria),
    }
