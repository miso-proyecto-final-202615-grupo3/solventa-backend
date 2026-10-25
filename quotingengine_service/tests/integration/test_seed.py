from sqlalchemy.ext.asyncio import AsyncSession

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
    assert set(reglas) == set(ids)
    for regla in reglas.values():
        assert regla.definicion["parametro_monto"] in {
            p["nombre"] for p in regla.definicion["parametros"]
        }


async def test_siembra_es_idempotente(db_session: AsyncSession):
    await sembrar_catalogo(db_session)

    assert await sembrar_catalogo(db_session) == 0
    assert len(await SqlAlchemyProductoSeguroRepository(db_session).listar_activos()) == 6
