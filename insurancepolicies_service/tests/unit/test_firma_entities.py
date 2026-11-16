import hashlib
import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest

from src.domain.firmas.entities import (
    ArchivoFirma,
    FirmaInvalidaError,
    calcular_fingerprint,
    construir_ruta,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"firma"
JPG = b"\xff\xd8\xff\xe0" + b"firma"


def test_valida_png_y_jpeg():
    ArchivoFirma(PNG, "image/png").validar(1024)
    ArchivoFirma(JPG, "image/jpeg").validar(1024)
    assert ArchivoFirma(PNG, "image/png").extension == "png"
    assert ArchivoFirma(JPG, "image/jpeg").extension == "jpg"


@pytest.mark.parametrize(
    ("contenido", "content_type", "codigo"),
    [
        (PNG, "image/gif", "FORMATO_NO_SOPORTADO"),
        (PNG, "application/pdf", "FORMATO_NO_SOPORTADO"),
        (b"", "image/png", "FIRMA_VACIA"),
        (JPG, "image/png", "FORMATO_NO_SOPORTADO"),
        (PNG + b"x" * 2000, "image/png", "FIRMA_DEMASIADO_GRANDE"),
    ],
)
def test_rechaza_archivos_invalidos(contenido, content_type, codigo):
    with pytest.raises(FirmaInvalidaError) as exc:
        ArchivoFirma(contenido, content_type).validar(1024)
    assert exc.value.codigo == codigo


def test_hash_es_sha256_del_contenido():
    assert ArchivoFirma(PNG, "image/png").hash == hashlib.sha256(PNG).hexdigest()
    assert ArchivoFirma(PNG, "image/png").hash != ArchivoFirma(PNG + b"x", "image/png").hash


def test_ruta_relativa_por_cliente_y_firma():
    cliente, firma = uuid.uuid4(), uuid.uuid4()

    assert construir_ruta(cliente, firma, "firma.png") == f"firma-digital/{cliente}/{firma}/firma.png"


def _fingerprint(**cambios):
    datos = {
        "firma_hash": "a" * 64,
        "capturada_en": datetime(2026, 11, 10, 12, 0, 0, 123456, tzinfo=UTC),
        "cliente_id": uuid.UUID(int=1),
        "cotizacion_id": uuid.UUID(int=2),
        "producto_id": uuid.UUID(int=3),
        "proveedor_firma": "CANVAS_MANUSCRITA",
    }
    datos.update(cambios)
    return calcular_fingerprint(**datos)


def test_fingerprint_es_determinista_y_normaliza_la_zona_horaria():
    bogota = timezone(timedelta(hours=-5))

    assert _fingerprint() == _fingerprint()
    assert _fingerprint() == _fingerprint(
        capturada_en=datetime(2026, 11, 10, 7, 0, 0, 123456, tzinfo=bogota)
    )


@pytest.mark.parametrize(
    "cambio",
    [
        {"firma_hash": "b" * 64},
        {"capturada_en": datetime(2026, 11, 10, 12, 0, 1, tzinfo=UTC)},
        {"cliente_id": uuid.UUID(int=9)},
        {"cotizacion_id": uuid.UUID(int=9)},
        {"producto_id": uuid.UUID(int=9)},
        {"proveedor_firma": "OTRO"},
    ],
)
def test_fingerprint_cambia_con_cada_campo(cambio):
    assert _fingerprint(**cambio) != _fingerprint()
