import json
from pathlib import Path

from src.presentation.schemas import PolizasElegiblesResponse, ReportarSiniestroRequest, SiniestroResponse

CONTRACTS = Path(__file__).resolve().parents[3] / "docs" / "contracts" / "siniestros"


def _muestra(nombre: str) -> dict:
    return json.loads((CONTRACTS / nombre).read_text(encoding="utf-8"))


def test_polizas_elegibles_cumple_el_contrato_canonico():
    respuesta = PolizasElegiblesResponse.model_validate(_muestra("polizas-elegibles.json"))

    poliza = respuesta.polizas[0]
    assert poliza.producto.codigo == "SEGURO_VIAJE"
    assert [t.codigo for t in poliza.tipos_siniestro] == ["GASTO_MEDICO", "EQUIPAJE", "CANCELACION_VIAJE"]
    assert poliza.tipos_siniestro[1].evidencia.videos_max == 1


def test_solicitud_y_respuesta_del_reporte_cumplen_el_contrato_canonico():
    solicitud = ReportarSiniestroRequest.model_validate(_muestra("reporte-request.json"))
    respuesta = SiniestroResponse.model_validate(_muestra("reporte-response.json"))

    assert solicitud.ocurrido_en.tzinfo is not None
    assert respuesta.estado == "REPORTADO"
    assert respuesta.poliza_id == solicitud.poliza_id
    assert respuesta.numero.startswith("SIN-")


def test_error_comun():
    error = _muestra("error-poliza-no-vigente.json")

    assert set(error) == {"codigo", "mensaje", "correlation_id"}
