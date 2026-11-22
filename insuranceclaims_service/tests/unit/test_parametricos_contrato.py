"""HU4.2.3 · Las muestras de docs/contracts/parametricos cumplen los esquemas de MS Siniestros."""
import json
from pathlib import Path

from src.presentation.routers.parametricos import EventoParametricoRequest, SuscripcionRequest
from src.domain.siniestros.parametricos import regla_para

CONTRACTS = Path(__file__).resolve().parents[3] / "docs" / "contracts" / "parametricos"


def _muestra(nombre: str) -> dict:
    return json.loads((CONTRACTS / nombre).read_text(encoding="utf-8"))


def test_eventos_de_ejemplo_son_validos_y_se_interpretan():
    for nombre in ("evento-lluvia-request.json", "evento-retraso-vuelo-request.json"):
        evento = EventoParametricoRequest.model_validate(_muestra(nombre))
        assert regla_para(evento.tipo).normalizar(evento.datos, evento.ocurrido_en).indice


def test_suscripcion_y_solicitud_de_pago():
    assert SuscripcionRequest.model_validate(_muestra("suscripcion-request.json")).cobertura.value == "LLUVIA_EXTREMA"
    pago = _muestra("pago-indemnizacion-solicitado.json")
    assert set(pago) == {
        "tipo", "indemnizacion_id", "siniestro_id", "numero", "poliza_id", "cliente_id", "monto", "moneda", "clave_idempotencia",
    }
