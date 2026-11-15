import json
from pathlib import Path

from src.presentation.schemas import (
    EvidenciaResponse,
    RegistrarUbicacionResponse,
    SiniestroDetalleResponse,
    SolicitudCargaRequest,
    SolicitudCargaResponse,
    UbicacionRequest,
)

CONTRACTS = Path(__file__).resolve().parents[3] / "docs" / "contracts" / "evidencias"


def _muestra(nombre: str) -> dict:
    return json.loads((CONTRACTS / nombre).read_text(encoding="utf-8"))


def test_solicitud_y_carga_cumplen_el_contrato():
    solicitud = SolicitudCargaRequest.model_validate(_muestra("solicitud-request.json"))
    respuesta = SolicitudCargaResponse.model_validate(_muestra("solicitud-response.json"))

    assert solicitud.capturada_en.tzinfo is not None
    assert respuesta.estado == "PENDIENTE"
    assert respuesta.carga.campos["key"].startswith("siniestros/")
    assert respuesta.carga.tamano_max_bytes == 5 * 1024 * 1024


def test_confirmacion_ubicacion_y_detalle_cumplen_el_contrato():
    confirmacion = EvidenciaResponse.model_validate(_muestra("confirmacion-response.json"))
    UbicacionRequest.model_validate(_muestra("ubicacion-request.json"))
    ubicacion = RegistrarUbicacionResponse.model_validate(_muestra("ubicacion-response.json"))
    detalle = SiniestroDetalleResponse.model_validate(_muestra("detalle-con-evidencias.json"))

    assert confirmacion.estado == "CARGADA"
    assert ubicacion.ubicacion.fuente == "GPS"
    assert [e.tipo for e in detalle.evidencias] == ["FOTO", "VIDEO"]


def test_error_comun():
    assert set(_muestra("error-limite-evidencias.json")) == {"codigo", "mensaje", "correlation_id"}
