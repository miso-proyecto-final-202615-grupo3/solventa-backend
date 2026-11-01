from src.infrastructure.providers.face_analyzer import FaceSignals
from src.infrastructure.providers.gesture_rules import validate_face_consistency, validate_gesture


def signal(**changes):
    values = {"face_count": 1, "blink_left": 0.1, "blink_right": 0.1, "yaw": 0.0, "interocular_ratio": 0.2}
    values.update(changes)
    return FaceSignals(**values)


def test_blink_requires_ojos_abiertos_cerrados_y_abiertos():
    assert validate_gesture("BLINK", [signal(), signal(blink_left=0.8, blink_right=0.8), signal()]) is None


def test_giro_izquierdo_requiere_desplazamiento_en_frame_central():
    assert validate_gesture("TURN_LEFT", [signal(), signal(yaw=25), signal()]) is None


def test_giro_derecho_con_los_angulos_medidos_en_dispositivo_real():
    # Motorola Edge 30 Fusion: TURN_RIGHT midió yaw 3 / -23 / 1.
    assert validate_gesture("TURN_RIGHT", [signal(yaw=3), signal(yaw=-23), signal(yaw=1)]) is None


def test_giro_en_direccion_contraria_se_rechaza():
    assert validate_gesture("TURN_RIGHT", [signal(), signal(yaw=25), signal()]) == "GESTO_NO_DETECTADO"
    assert validate_gesture("TURN_LEFT", [signal(), signal(yaw=-25), signal()]) == "GESTO_NO_DETECTADO"


def test_el_signo_es_configurable():
    assert validate_gesture("TURN_RIGHT", [signal(), signal(yaw=25), signal()], right_turn_sign=1) is None


def test_rechaza_rostro_inconsistente():
    assert validate_face_consistency([signal(), signal(interocular_ratio=0.4), signal()], 0.25) == "ROSTRO_INCONSISTENTE"
