import hashlib
import secrets
import uuid

from src.application.ports import ProviderSessionStarted, ProviderUnavailableError, ProviderVerificationResult
from src.core.config import settings
from src.infrastructure.providers.face_analyzer import MediaPipeFaceAnalyzer
from src.infrastructure.providers.gesture_rules import validate_face_consistency, validate_gesture


class PropioProvider:
    """Proveedor local que emite un reto y aplica validaciones de evidencia básicas."""

    name = "propio"

    def __init__(self, analyzer=None) -> None:
        self._analyzer = analyzer or MediaPipeFaceAnalyzer(settings.PROPIO_MODEL_PATH)

    def start_session(self) -> ProviderSessionStarted:
        return ProviderSessionStarted(
            capture={
                "tipo": "FRAMES",
                "reto": {
                    "gesto": secrets.choice(("BLINK", "TURN_LEFT", "TURN_RIGHT")),
                    "nonce": secrets.token_urlsafe(24),
                },
            }
        )

    def verify(self, session: dict, frames: dict[str, bytes]) -> ProviderVerificationResult:
        expected = {"frame_inicio", "frame_gesto", "frame_fin"}
        if set(frames) != expected:
            return ProviderVerificationResult("", False, "CAPTURA_INVALIDA")
        fingerprints = {hashlib.sha256(frame).digest() for frame in frames.values()}
        if len(fingerprints) != len(expected):
            return ProviderVerificationResult("", False, "CAPTURA_INVALIDA")
        try:
            signals = [self._analyzer.analyze(frames[name]) for name in ("frame_inicio", "frame_gesto", "frame_fin")]
        except RuntimeError as exc:
            raise ProviderUnavailableError() from exc
        if any(signal.face_width_ratio < settings.PROPIO_MIN_FACE_WIDTH_RATIO for signal in signals):
            return ProviderVerificationResult("", False, "ROSTRO_NO_DETECTADO")
        reason = validate_face_consistency(signals, settings.PROPIO_MAX_INTEROCULAR_VARIATION)
        if reason:
            return ProviderVerificationResult("", False, reason)
        reason = validate_gesture(session.get("gesture", ""), signals)
        if reason:
            return ProviderVerificationResult("", False, reason)
        return ProviderVerificationResult(f"propio-{uuid.uuid4()}", True)
