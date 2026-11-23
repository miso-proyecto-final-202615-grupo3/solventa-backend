"""HU4.2.2 · Las muestras de docs/contracts/notificaciones cumplen el contrato canónico (§3)."""
import json
from pathlib import Path

from src.presentation.schemas import RegistrarPushRequest

CONTRACTS = Path(__file__).resolve().parents[3] / "docs" / "contracts" / "notificaciones"


def _muestra(nombre: str) -> dict:
    return json.loads((CONTRACTS / nombre).read_text(encoding="utf-8"))


def test_registro_del_token():
    registro = RegistrarPushRequest.model_validate(_muestra("registro-push-request.json"))

    assert registro.plataforma == "ANDROID"


def test_destinos_y_mensaje():
    destinos = _muestra("destinos-push-response.json")["destinos"]
    mensaje = _muestra("mensaje-siniestro-estado.json")

    assert set(destinos[0]) == {"installation_id", "token", "plataforma"}
    assert set(mensaje) == {"tipo", "siniestro_id", "numero", "estado", "evento_id"}
    assert mensaje["tipo"] == "SINIESTRO_ESTADO"
    assert all(isinstance(valor, str) for valor in mensaje.values())  # FCM solo admite datos de texto


def test_cambio_de_estado_y_error_comun():
    assert _muestra("cambio-estado-request.json") == {"estado": "EN_EVALUACION"}
    assert set(_muestra("error-dispositivo-no-vinculado.json")) == {"codigo", "mensaje", "correlation_id"}
