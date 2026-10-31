from dataclasses import dataclass
from math import atan2, degrees, hypot
from pathlib import Path
from threading import Lock


@dataclass(frozen=True)
class FaceSignals:
    face_count: int
    blink_left: float = 0.0
    blink_right: float = 0.0
    yaw: float = 0.0
    pitch: float = 0.0
    face_width_ratio: float = 0.0
    interocular_ratio: float = 0.0


class MediaPipeFaceAnalyzer:
    """Analizador local; no conserva ni registra imágenes biométricas."""

    def __init__(self, model_path: str) -> None:
        self._model_path = model_path
        self._detector = None
        self._lock = Lock()

    def analyze(self, image: bytes) -> FaceSignals:
        detector = self._get_detector()
        try:
            import mediapipe as mp
            import numpy as np
            from PIL import Image, ImageOps
            from io import BytesIO

            with Image.open(BytesIO(image)) as opened:
                normalized = ImageOps.exif_transpose(opened).convert("RGB")
                width, height = normalized.size
                result = detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.asarray(normalized)))
            count = len(result.face_landmarks)
            if count != 1:
                return FaceSignals(face_count=count)
            landmarks = result.face_landmarks[0]
            xs = [point.x for point in landmarks]
            face_width = max(xs) - min(xs)
            left, right = landmarks[33], landmarks[263]
            interocular = hypot(left.x - right.x, left.y - right.y)
            blendshapes = {item.category_name: item.score for item in result.face_blendshapes[0]}
            yaw = 0.0
            pitch = 0.0
            if result.facial_transformation_matrixes:
                matrix = result.facial_transformation_matrixes[0]
                values = getattr(matrix, "data", matrix)
                values = list(values.flatten()) if hasattr(values, "flatten") else list(values)
                if len(values) >= 16:
                    yaw = degrees(atan2(values[2], values[10]))
                    pitch = degrees(atan2(-values[6], (values[10] ** 2 + values[2] ** 2) ** 0.5))
            return FaceSignals(
                face_count=1,
                blink_left=blendshapes.get("eyeBlinkLeft", 0.0),
                blink_right=blendshapes.get("eyeBlinkRight", 0.0),
                yaw=yaw,
                pitch=pitch,
                face_width_ratio=face_width,
                interocular_ratio=interocular,
            )
        except Exception as exc:
            raise RuntimeError("No fue posible analizar la evidencia facial.") from exc

    def _get_detector(self):
        with self._lock:
            if self._detector is not None:
                return self._detector
            if not Path(self._model_path).is_file():
                raise RuntimeError("Modelo facial no disponible.")
            from mediapipe.tasks import python
            from mediapipe.tasks.python import vision

            options = vision.FaceLandmarkerOptions(
                base_options=python.BaseOptions(model_asset_path=self._model_path),
                output_face_blendshapes=True,
                output_facial_transformation_matrixes=True,
                num_faces=2,
            )
            self._detector = vision.FaceLandmarker.create_from_options(options)
            return self._detector
