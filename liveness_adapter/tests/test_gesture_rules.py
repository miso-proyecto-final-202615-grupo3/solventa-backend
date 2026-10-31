from src.infrastructure.providers.face_analyzer import FaceSignals
from src.infrastructure.providers.gesture_rules import validate_face_consistency, validate_gesture


def signal(**changes):
    values = {"face_count": 1, "blink_left": 0.1, "blink_right": 0.1, "yaw": 0.0, "interocular_ratio": 0.2}
    values.update(changes)
    return FaceSignals(**values)


def test_blink_requires_ojos_abiertos_cerrados_y_abiertos():
    assert validate_gesture("BLINK", [signal(), signal(blink_left=0.8, blink_right=0.8), signal()]) is None


def test_giro_izquierdo_requiere_desplazamiento_en_frame_central():
    assert validate_gesture("TURN_LEFT", [signal(), signal(yaw=-25), signal()]) is None


def test_rechaza_rostro_inconsistente():
    assert validate_face_consistency([signal(), signal(interocular_ratio=0.4), signal()], 0.25) == "ROSTRO_INCONSISTENTE"
