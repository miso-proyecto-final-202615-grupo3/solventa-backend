from src.infrastructure.providers.face_analyzer import FaceSignals


def validate_face_consistency(signals: list[FaceSignals], max_variation: float) -> str | None:
    if any(signal.face_count == 0 for signal in signals):
        return "ROSTRO_NO_DETECTADO"
    if any(signal.face_count > 1 for signal in signals):
        return "VARIOS_ROSTROS"
    baseline = signals[0].interocular_ratio
    if baseline <= 0 or any(abs(signal.interocular_ratio - baseline) / baseline > max_variation for signal in signals[1:]):
        return "ROSTRO_INCONSISTENTE"
    return None


def validate_gesture(gesture: str, signals: list[FaceSignals]) -> str | None:
    first, middle, last = signals
    if gesture == "BLINK":
        open_eyes = lambda value: value.blink_left < 0.35 and value.blink_right < 0.35
        closed_eyes = middle.blink_left > 0.55 and middle.blink_right > 0.55
        return None if open_eyes(first) and closed_eyes and open_eyes(last) else "GESTO_NO_DETECTADO"
    if gesture == "TURN_LEFT":
        return None if abs(first.yaw) < 12 and middle.yaw < -20 and abs(last.yaw) < 12 else "GESTO_NO_DETECTADO"
    if gesture == "TURN_RIGHT":
        return None if abs(first.yaw) < 12 and middle.yaw > 20 and abs(last.yaw) < 12 else "GESTO_NO_DETECTADO"
    return "GESTO_NO_DETECTADO"
