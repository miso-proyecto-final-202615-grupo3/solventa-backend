import hashlib
import secrets
import uuid

from src.application.ports import ProviderSessionStarted, ProviderVerificationResult


class PropioProvider:
    """Proveedor local que emite un reto y aplica validaciones de evidencia básicas."""

    name = "propio"

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
        return ProviderVerificationResult(f"propio-{uuid.uuid4()}", True)
