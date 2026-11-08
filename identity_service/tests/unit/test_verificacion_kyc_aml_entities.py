import uuid
from datetime import UTC, datetime

import pytest

from src.domain.verificaciones_kyc_aml.entities import (
    ArchivoDocumento,
    DocumentoInvalidoError,
    EstadoVerificacion,
    ResultadoChequeo,
    ResultadoProveedor,
    VerificacionKycAml,
)

A, R, P = ResultadoChequeo.APROBADO, ResultadoChequeo.RECHAZADO, ResultadoChequeo.PENDIENTE


def _verificacion() -> VerificacionKycAml:
    return VerificacionKycAml(
        id=uuid.uuid4(), cliente_id=uuid.uuid4(), proveedor="mock_kyc", huella_documentos="h",
        ruta_documento_frontal="f", ruta_documento_reverso="r",
        iniciada_en=datetime.now(UTC), correlation_id="c",
    )


@pytest.mark.parametrize(
    ("kyc", "aml", "estado"),
    [
        (A, A, EstadoVerificacion.APROBADA),
        (A, R, EstadoVerificacion.RECHAZADA),
        (R, A, EstadoVerificacion.RECHAZADA),
        (R, P, EstadoVerificacion.RECHAZADA),
        (P, A, EstadoVerificacion.INICIANDO),
    ],
)
def test_estado_depende_de_ambos_chequeos(kyc, aml, estado):
    v = _verificacion()

    v.aplicar_resultado(ResultadoProveedor(kyc, aml, {}), datetime.now(UTC))

    assert v.estado == estado
    assert (v.resultado_en is not None) == v.es_final


@pytest.mark.parametrize(
    ("contenido", "tipo", "codigo"),
    [
        (b"\xff\xd8\xff", "image/gif", "FORMATO_NO_SOPORTADO"),
        (b"", "image/jpeg", "DOCUMENTO_VACIO"),
        (b"\xff\xd8\xff" + b"0" * 10, "image/jpeg", "DOCUMENTO_DEMASIADO_GRANDE"),
        (b"\x89PNG\r\n\x1a\n", "image/jpeg", "FORMATO_NO_SOPORTADO"),
    ],
)
def test_documento_invalido(contenido, tipo, codigo):
    with pytest.raises(DocumentoInvalidoError) as exc:
        ArchivoDocumento(contenido, tipo).validar(12)

    assert exc.value.codigo == codigo


def test_documento_valido():
    ArchivoDocumento(b"\x89PNG\r\n\x1a\n", "image/png").validar(100)
