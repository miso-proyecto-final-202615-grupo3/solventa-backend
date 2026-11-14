import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.domain.siniestros.catalogo import ReglasEvidencia
from src.domain.siniestros.entities import Siniestro
from src.domain.siniestros.errores import (
    EvidenciaDemasiadoGrande,
    FormatoNoSoportado,
    LimiteEvidencias,
    SiniestroNoAdmiteEvidencias,
    TipoEvidenciaNoPermitido,
    TransicionInvalida,
)
from src.domain.siniestros.evidencias import EstadoEvidencia, EvidenciaSiniestro, TipoEvidencia, clave_objeto
from src.domain.siniestros.politica_evidencias import MB, PoliticaEvidencias
from src.domain.siniestros.ubicacion import FuenteUbicacion, UbicacionInvalida, UbicacionSiniestro

AHORA = datetime(2026, 11, 10, 20, 0, tzinfo=UTC)


def _siniestro(estado: str = "REPORTADO") -> Siniestro:
    return Siniestro(
        poliza_id=uuid.uuid4(), tipo="EQUIPAJE", estado=estado, clave_idempotencia="k",
        ocurrido_en=AHORA, reportado_en=AHORA, producto_codigo="SEGURO_VIAJE",
    )


def _evidencia(**cambios) -> EvidenciaSiniestro:
    datos = dict(
        siniestro_id=uuid.uuid4(), tipo="FOTO", content_type="image/jpeg", tamano_declarado=100, origen="CAMARA",
        capturada_en=AHORA, objeto_clave="k", estado="PENDIENTE", solicitada_en=AHORA,
        expira_en=AHORA + timedelta(minutes=10),
    )
    datos.update(cambios)
    return EvidenciaSiniestro(**datos)


# --- Máquina de estados ---------------------------------------------------------------------------

def test_confirmar_y_no_volver_a_cambiar():
    evidencia = _evidencia()

    evidencia.confirmar(100, AHORA)

    assert evidencia.estado == EstadoEvidencia.CARGADA.value
    assert evidencia.tamano_bytes == 100 and evidencia.cargada_en == AHORA
    with pytest.raises(TransicionInvalida):
        evidencia.rechazar("x")


def test_rechazar_guarda_el_motivo():
    evidencia = _evidencia()

    evidencia.rechazar("TAMANO_DISTINTO")

    assert evidencia.estado == "RECHAZADA" and evidencia.motivo_rechazo == "TAMANO_DISTINTO"
    with pytest.raises(TransicionInvalida):
        evidencia.confirmar(1, AHORA)


def test_expira_solo_si_esta_pendiente_y_vencida():
    evidencia = _evidencia()

    assert not evidencia.expirar_si_vencida(AHORA + timedelta(minutes=9, seconds=59))
    assert evidencia.expirar_si_vencida(AHORA + timedelta(minutes=10))
    assert evidencia.estado == "EXPIRADA"
    assert not evidencia.expirar_si_vencida(AHORA + timedelta(days=1))


def test_vencida_acepta_fechas_sin_zona_de_sqlite():
    evidencia = _evidencia(expira_en=datetime(2026, 11, 10, 20, 5))

    assert evidencia.vencida(AHORA + timedelta(minutes=6))


def test_la_clave_no_contiene_datos_del_cliente():
    siniestro_id, evidencia_id = uuid.uuid4(), uuid.uuid4()

    assert clave_objeto("siniestros/", siniestro_id, evidencia_id, TipoEvidencia.VIDEO) == (
        f"siniestros/{siniestro_id}/evidencias/{evidencia_id}.mp4"
    )


# --- Política --------------------------------------------------------------------------------------

REGLAS = ReglasEvidencia(fotos_max=5, videos_max=1)
SIN_VIDEO = ReglasEvidencia(fotos_max=5, videos_max=0)


def _validar(siniestro=None, reglas=REGLAS, tipo=TipoEvidencia.FOTO, ct="image/jpeg", tamano=1000, vigentes=0):
    PoliticaEvidencias().validar_solicitud(siniestro or _siniestro(), reglas, tipo, ct, tamano, vigentes)


def test_politica_acepta_una_solicitud_valida():
    _validar()
    _validar(tipo=TipoEvidencia.VIDEO, ct="video/mp4", tamano=50 * MB)


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"siniestro": _siniestro("EN_EVALUACION")}, SiniestroNoAdmiteEvidencias),
        ({"reglas": SIN_VIDEO, "tipo": TipoEvidencia.VIDEO, "ct": "video/mp4"}, TipoEvidenciaNoPermitido),
        ({"ct": "image/png"}, FormatoNoSoportado),
        ({"tipo": TipoEvidencia.VIDEO, "ct": "video/quicktime"}, FormatoNoSoportado),
        ({"tamano": 5 * MB + 1}, EvidenciaDemasiadoGrande),
        ({"tipo": TipoEvidencia.VIDEO, "ct": "video/mp4", "tamano": 50 * MB + 1}, EvidenciaDemasiadoGrande),
        ({"vigentes": 5}, LimiteEvidencias),
        ({"tipo": TipoEvidencia.VIDEO, "ct": "video/mp4", "vigentes": 1}, LimiteEvidencias),
    ],
)
def test_politica_rechaza(kwargs, error):
    with pytest.raises(error):
        _validar(**kwargs)


def test_el_tamano_maximo_es_inclusivo():
    _validar(tamano=5 * MB)


@pytest.mark.parametrize(
    ("tipo", "datos", "valida"),
    [
        (TipoEvidencia.FOTO, b"\xff\xd8\xff\xe0" + b"\x00" * 8, True),
        (TipoEvidencia.FOTO, b"\x89PNG\r\n\x1a\n" + b"\x00" * 4, False),
        (TipoEvidencia.VIDEO, b"\x00\x00\x00\x18ftypmp42", True),
        (TipoEvidencia.VIDEO, b"\xff\xd8\xff\xe0" + b"\x00" * 8, False),
    ],
)
def test_firma_de_bytes(tipo, datos, valida):
    assert PoliticaEvidencias.firma_valida(tipo, datos) is valida


# --- Ubicación -------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("lat", "lon", "precision"),
    [(91, 0, 10), (-91, 0, 10), (0, 181, 10), (0, -181, 10), (0, 0, 0), (0, 0, 5001)],
)
def test_ubicacion_fuera_de_rango(lat, lon, precision):
    with pytest.raises(UbicacionInvalida):
        UbicacionSiniestro(lat, lon, precision, FuenteUbicacion.GPS, AHORA)


def test_registrar_ubicacion_reemplaza_y_redondea():
    siniestro = _siniestro()
    siniestro.registrar_ubicacion(UbicacionSiniestro(4.65331234, -74.08361234, 18.456, FuenteUbicacion.RED, AHORA), AHORA)
    siniestro.registrar_ubicacion(UbicacionSiniestro(4.7, -74.1, 10, FuenteUbicacion.GPS, AHORA), AHORA)

    ubicacion = siniestro.ubicacion
    assert (ubicacion.latitud, ubicacion.longitud, ubicacion.fuente) == (4.7, -74.1, FuenteUbicacion.GPS)
    assert siniestro.ubicacion_actualizada_en == AHORA


def test_sin_ubicacion_es_none():
    assert _siniestro().ubicacion is None
