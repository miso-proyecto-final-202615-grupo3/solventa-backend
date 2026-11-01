from math import cos, radians, sin

import numpy as np
import pytest

from src.infrastructure.providers.face_analyzer import head_pose


def _yaw_matrix(angle: float) -> np.ndarray:
    """Rotación pura en Y, como la entrega MediaPipe 1.x (ndarray float32 4x4)."""
    a = radians(angle)
    return np.array(
        [[cos(a), 0, sin(a), 0], [0, 1, 0, 0], [-sin(a), 0, cos(a), -40], [0, 0, 0, 1]],
        dtype=np.float32,
    )


@pytest.mark.parametrize("angle", [-30.0, 0.0, 25.0])
def test_lee_el_yaw_de_un_ndarray_4x4(angle):
    yaw, pitch = head_pose(_yaw_matrix(angle))

    assert yaw == pytest.approx(angle, abs=0.01)
    assert pitch == pytest.approx(0.0, abs=0.01)


def test_acepta_la_matriz_como_lista_plana():
    yaw, _ = head_pose(_yaw_matrix(20.0).reshape(-1).tolist())

    assert yaw == pytest.approx(20.0, abs=0.01)


def test_matriz_incompleta_no_rompe_el_analisis():
    assert head_pose([1.0, 0.0]) == (0.0, 0.0)
