"""Datos y utilidades para probar la generación real del certificado PDF."""
import io
import struct
import zlib
from typing import Any

import pytest


def weasyprint_disponible() -> bool:
    # WeasyPrint necesita librerías nativas (Pango): sin ellas se omiten las pruebas de render.
    try:
        import weasyprint  # noqa: F401
    except (ImportError, OSError):
        return False
    return True


requiere_weasyprint = pytest.mark.skipif(
    not weasyprint_disponible(), reason="WeasyPrint o sus librerías nativas no están disponibles"
)


def png(ancho: int = 120, alto: int = 40) -> bytes:
    """PNG RGBA válido (trazo negro sobre transparente) sin depender de Pillow."""

    def chunk(tipo: bytes, datos: bytes) -> bytes:
        cuerpo = tipo + datos
        return struct.pack(">I", len(datos)) + cuerpo + struct.pack(">I", zlib.crc32(cuerpo))

    filas = b""
    for y in range(alto):
        fila = bytearray()
        for x in range(ancho):
            trazo = abs(y - (alto // 2 + int(8 * ((x % 20) - 10) / 10))) < 2
            fila += bytes((0, 0, 0, 255)) if trazo else bytes((0, 0, 0, 0))
        filas += b"\x00" + bytes(fila)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", ancho, alto, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(filas))
        + chunk(b"IEND", b"")
    )


def datos_certificado(coberturas: int = 2, **cambios: Any) -> dict[str, Any]:
    datos: dict[str, Any] = {
        "poliza": {
            "poliza_id": "9b2f6a0e-1c3d-4e5f-8a7b-0c1d2e3f4a5b",
            "numero": "POL-20261113-AB12CD34",
            "estado": "EMITIDA",
            "ramo": "VIDA",
            "emitida_en": "2026-11-13",
            "vigencia_desde": "2026-11-13",
            "vigencia_hasta": "2036-11-13",
        },
        "titular": {
            "nombre": "María Fernanda Rodríguez Castañeda",
            "tipo_documento": "CC",
            "numero_identificacion": "1020304050",
        },
        "producto": {
            "codigo": "VIDA_HIPOTECARIO",
            "nombre": "Seguro de Vida Deudores Hipotecarios",
            "ramo": "VIDA",
        },
        "moneda": "COP",
        "coberturas": [
            {
                "cobertura_id": f"c{i}",
                "codigo": f"COB_{i}",
                "nombre": f"Cobertura número {i}",
                "limite_asegurado": "200000000.00",
                "deducible": "1500000.00",
                "prima": "425000.50",
            }
            for i in range(coberturas)
        ],
        "prima": {
            "base": "1000000.00",
            "neta": "1190000.00",
            "impuestos": [{"concepto": "IVA", "tasa": "0.19", "valor": "226100.00"}],
            "total": "1416100.00",
        },
        "condiciones": {"version_generales": "1.0", "aceptadas_en": "2026-11-12"},
        "firma": {
            "firma_id": "f1",
            "capturada_en": "2026-11-12",
            "proveedor": "CANVAS_MANUSCRITA",
            "firma_hash": "a" * 64,
            "fingerprint_contrato": "b3f1c2d4e5a60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90",
        },
        "generado_en": "2026-11-13",
    }
    datos.update(cambios)
    return datos


def texto_pdf(pdf: bytes) -> str:
    from pypdf import PdfReader

    lector = PdfReader(io.BytesIO(pdf))
    return " ".join(" ".join(pagina.extract_text().split()) for pagina in lector.pages)


def paginas_pdf(pdf: bytes) -> int:
    from pypdf import PdfReader

    return len(PdfReader(io.BytesIO(pdf)).pages)


def imagenes_pdf(pdf: bytes) -> int:
    from pypdf import PdfReader

    return sum(len(pagina.images) for pagina in PdfReader(io.BytesIO(pdf)).pages)
