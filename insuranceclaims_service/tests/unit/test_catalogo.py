import pytest
from sqlalchemy import func, select

from src.domain.siniestros.catalogo import idioma_de
from src.infrastructure.persistence.catalogo_tipos_siniestro_impl import (
    SqlAlchemyCatalogoTiposSiniestro,
    invalidar_cache,
)
from src.infrastructure.persistence.models import TipoSiniestroModel
from src.infrastructure.persistence.seed_tipos_siniestro import TIPOS_SINIESTRO, sembrar_tipos_siniestro


@pytest.fixture
async def catalogo(db_session):
    invalidar_cache()
    await sembrar_tipos_siniestro(db_session)
    yield SqlAlchemyCatalogoTiposSiniestro(db_session)
    invalidar_cache()


async def test_la_semilla_es_idempotente(db_session):
    primera = await sembrar_tipos_siniestro(db_session)
    segunda = await sembrar_tipos_siniestro(db_session)

    total = await db_session.scalar(select(func.count()).select_from(TipoSiniestroModel))
    assert primera == len(TIPOS_SINIESTRO)
    assert segunda == 0
    assert total == len(TIPOS_SINIESTRO)


async def test_tipos_de_un_producto_en_orden_de_pantalla(catalogo):
    tipos = await catalogo.tipos_de("SEGURO_VIAJE")

    assert [t.codigo for t in tipos] == ["GASTO_MEDICO", "EQUIPAJE", "CANCELACION_VIAJE"]
    assert tipos[0].reglas.fotos_max == 5
    assert not tipos[0].reglas.admite_video
    assert tipos[1].reglas.admite_video


@pytest.mark.parametrize("producto", ["MICROSEGURO_VIDA", "VIDA_HIPOTECARIO", "NO_EXISTE"])
async def test_productos_sin_tipos_no_se_reportan_por_la_app(catalogo, producto):
    assert await catalogo.tipos_de(producto) == []


async def test_obtener_un_tipo_y_uno_inexistente(catalogo):
    robo = await catalogo.obtener("PROTECCION_DISPOSITIVOS", "ROBO")

    assert robo is not None and robo.nombre == "Robo"
    assert await catalogo.obtener("PROTECCION_DISPOSITIVOS", "GASTO_MEDICO") is None


async def test_nombre_en_ingles(catalogo):
    robo = await catalogo.obtener("PROTECCION_DISPOSITIVOS", "ROBO", idioma="en")

    assert robo.nombre == "Theft"


async def test_los_tipos_inactivos_no_se_listan(db_session, catalogo):
    modelo = await db_session.scalar(select(TipoSiniestroModel).where(TipoSiniestroModel.codigo == "ROBO"))
    modelo.activo = False
    await db_session.flush()
    invalidar_cache()

    codigos = [t.codigo for t in await catalogo.tipos_de("PROTECCION_DISPOSITIVOS")]

    assert codigos == ["DANO_DISPOSITIVO"]


async def test_listar_todos_los_productos(catalogo):
    assert len(await catalogo.listar()) == len(TIPOS_SINIESTRO)


@pytest.mark.parametrize(
    ("header", "idioma"),
    [(None, "es"), ("", "es"), ("es-CO,es;q=0.9", "es"), ("en-US,en;q=0.9", "en"), ("EN", "en"), ("fr", "es")],
)
def test_idioma_desde_accept_language(header, idioma):
    assert idioma_de(header) == idioma
