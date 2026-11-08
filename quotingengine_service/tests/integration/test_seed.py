from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update

from src.infrastructure.persistence.cobertura_repository_impl import (
    SqlAlchemyCoberturaRepository,
)
from src.infrastructure.persistence.producto_seguro_repository_impl import (
    SqlAlchemyProductoSeguroRepository,
)
from src.infrastructure.persistence.regla_rating_repository_impl import (
    SqlAlchemyReglaRatingRepository,
)
from src.infrastructure.persistence.seed import CATALOGO, sembrar_catalogo
from src.infrastructure.persistence.models import ProductoSeguroModel


async def test_siembra_seis_productos_con_coberturas_y_reglas(db_session: AsyncSession):
    assert await sembrar_catalogo(db_session) == 6

    productos = await SqlAlchemyProductoSeguroRepository(db_session).listar_activos()
    ids = [p.producto_id for p in productos]
    coberturas = await SqlAlchemyCoberturaRepository(
        db_session
    ).listar_activas_por_productos(ids)
    reglas = await SqlAlchemyReglaRatingRepository(
        db_session
    ).obtener_vigentes_por_productos(ids)

    assert len(productos) == 6
    assert {p.codigo for p in productos} == {c["codigo"] for c in CATALOGO}
    assert all(coberturas[i] for i in ids)
    assert all(p.condiciones_generales and p.version_condiciones_generales == "1.0" for p in productos)
    assert set(reglas) == set(ids)
    for regla in reglas.values():
        assert regla.definicion["parametro_monto"] in {
            p["nombre"] for p in regla.definicion["parametros"]
        }


async def test_siembra_es_idempotente(db_session: AsyncSession):
    await sembrar_catalogo(db_session)

    assert await sembrar_catalogo(db_session) == 0
    assert len(await SqlAlchemyProductoSeguroRepository(db_session).listar_activos()) == 6


async def test_siembra_inicializa_productos_existentes_sin_reemplazar_condiciones(db_session: AsyncSession):
    await sembrar_catalogo(db_session)
    await db_session.execute(update(ProductoSeguroModel).where(
        ProductoSeguroModel.codigo == "SEGURO_VIAJE"
    ).values(condiciones_generales=None, version_condiciones_generales=None))
    await db_session.execute(update(ProductoSeguroModel).where(
        ProductoSeguroModel.codigo == "MICROSEGURO_VIDA"
    ).values(condiciones_generales="Condiciones propias", version_condiciones_generales="2.0"))
    await db_session.commit()
    assert await sembrar_catalogo(db_session) == 0
    repo = SqlAlchemyProductoSeguroRepository(db_session)
    viaje = await repo.obtener_por_codigo("SEGURO_VIAJE")
    vida = await repo.obtener_por_codigo("MICROSEGURO_VIDA")
    assert viaje.condiciones_generales and viaje.version_condiciones_generales == "1.0"
    assert vida.condiciones_generales == "Condiciones propias"
    assert vida.version_condiciones_generales == "2.0"
