from datetime import UTC, datetime
from sqlalchemy import select

from src.domain.socios.entities import EventoSocio, Socio
from src.infrastructure.persistence.models import EventoSocioModel, SocioModel
from src.infrastructure.persistence.socio_repository_impl import SqlAlchemySocioRepository


async def test_registra_socio_y_evento_en_la_misma_transaccion(db_session):
    fecha = datetime.now(UTC)
    socio, evento = Socio.registrar(
            nombre="Banco Andino",
            correo="socio@yopmail.com",
        tipo_socio="Banco",
        canal_integracion="API",
        registrado_por="operator-123",
        creado_en=fecha,
    )

    await SqlAlchemySocioRepository(db_session).registrar(socio, evento)

    socios = (await db_session.execute(select(SocioModel))).scalars().all()
    eventos = (await db_session.execute(select(EventoSocioModel))).scalars().all()
    assert len(socios) == 1
    assert socios[0].id == socio.id
    assert socios[0].estado == "ACTIVO"
    assert socios[0].registrado_por == "operator-123"
    assert len(eventos) == 1
    assert eventos[0].socio_id == socio.id
    assert eventos[0].accion == "REGISTRO"
    assert eventos[0].actor_id == "operator-123"
