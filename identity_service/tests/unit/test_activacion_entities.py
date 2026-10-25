from datetime import UTC, datetime, timedelta
from uuid import uuid4

from src.domain.activacion_movil.entities import (
    DatosDispositivo,
    EstadoSesion,
    Plataforma,
    SesionActivacion,
)


def test_sesion_de_activacion_conserva_datos_del_dispositivo():
    dispositivo = DatosDispositivo(
        installation_id=uuid4(),
        plataforma=Plataforma.ANDROID,
        modelo="Pixel 9",
        version_so="15",
    )
    creada_en = datetime.now(UTC)
    sesion = SesionActivacion(
        id="sesion-1",
        cliente_id=uuid4(),
        dispositivo=dispositivo,
        tipo_captura="FRAMES",
        estado=EstadoSesion.CREADA,
        creada_en=creada_en,
        expira_en=creada_en + timedelta(minutes=2),
    )

    assert sesion.dispositivo == dispositivo
    assert sesion.estado is EstadoSesion.CREADA
