import hashlib
import logging
import secrets
import uuid

from src.application.ports import ProviderSessionStarted, ProviderUnavailableError, ProviderVerificationResult
from src.core.config import settings
from src.infrastructure.providers.face_analyzer import MediaPipeFaceAnalyzer
from src.infrastructure.providers.gesture_rules import validate_face_consistency, validate_gesture

logger = logging.getLogger("uvicorn.error")


class PropioProvider:
    """Proveedor local que emite un reto y aplica validaciones de evidencia básicas."""

    name = "propio"
    capture_type = "FRAMES"
    requires_budget = False

    def __init__(self, analyzer=None) -> None:
        self._analyzer = analyzer or MediaPipeFaceAnalyzer(settings.PROPIO_MODEL_PATH)

    def warm_up(self) -> None:
        warm_up = getattr(self._analyzer, "warm_up", None)
        if warm_up is not None:
            warm_up()

    def start_session(self, customer_id: str, session_id: str) -> ProviderSessionStarted:
        return ProviderSessionStarted(
            capture={
                "tipo": "FRAMES",
                "reto": {
                    "gesto": secrets.choice(("BLINK", "TURN_LEFT", "TURN_RIGHT")),
                    "nonce": secrets.token_urlsafe(24),
                },
            }
        )

    def verify(
        self, session: dict, frames: dict[str, bytes], sdk_result: str | None = None
    ) -> ProviderVerificationResult:
        expected = {"frame_inicio", "frame_gesto", "frame_fin"}
        if set(frames) != expected:
            return ProviderVerificationResult("", False, "CAPTURA_INVALIDA")
        fingerprints = {hashlib.sha256(frame).digest() for frame in frames.values()}
        if len(fingerprints) != len(expected):
            return ProviderVerificationResult("", False, "CAPTURA_INVALIDA")
        try:
            signals = [self._analyzer.analyze(frames[name]) for name in ("frame_inicio", "frame_gesto", "frame_fin")]
        except RuntimeError as exc:
            # Solo el tipo de error: nunca la imagen ni datos del cliente.
            cause = exc.__cause__ or exc
            logger.warning("propio_analysis_failed error=%s detail=%s", type(cause).__name__, str(cause)[:120])
            raise ProviderUnavailableError() from exc
        if any(signal.face_width_ratio < settings.PROPIO_MIN_FACE_WIDTH_RATIO for signal in signals):
            return ProviderVerificationResult("", False, "ROSTRO_NO_DETECTADO")
        reason = validate_face_consistency(signals, settings.PROPIO_MAX_INTEROCULAR_VARIATION)
        if reason:
            return ProviderVerificationResult("", False, reason)
        reason = validate_gesture(session.get("gesture", ""), signals, settings.PROPIO_RIGHT_TURN_YAW_SIGN)
        if reason:
            # Diagnóstico para calibrar umbrales: solo ángulos y puntajes redondeados, sin imagen.
            logger.info(
                "propio_gesture_rejected gesture=%s yaw=%s blink=%s",
                session.get("gesture", ""),
                "/".join(f"{signal.yaw:.0f}" for signal in signals),
                "/".join(f"{signal.blink_left:.2f}-{signal.blink_right:.2f}" for signal in signals),
            )
            return ProviderVerificationResult("", False, reason)
        return ProviderVerificationResult(f"propio-{uuid.uuid4()}", True)
