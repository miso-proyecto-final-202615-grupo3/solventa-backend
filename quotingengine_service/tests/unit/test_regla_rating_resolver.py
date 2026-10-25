import uuid
from datetime import datetime, timezone

from src.application.services.regla_rating_resolver import ReglaRatingResolver
from src.domain.reglas_rating.entities import ReglaRating
from src.domain.reglas_rating.repositories import ReglaRatingRepository


class RepoFalso(ReglaRatingRepository):
    def __init__(self, reglas: list[ReglaRating]) -> None:
        self.reglas = {r.producto_id: r for r in reglas}
        self.consultas = 0

    async def guardar(self, regla):
        raise NotImplementedError

    async def obtener_vigente_por_producto(self, producto_id):
        self.consultas += 1
        return self.reglas.get(producto_id)

    async def obtener_vigentes_por_productos(self, producto_ids):
        self.consultas += 1
        return {i: self.reglas[i] for i in producto_ids if i in self.reglas}

    async def existe_por_producto(self, producto_id):
        return producto_id in self.reglas


class CacheFalso:
    def __init__(self) -> None:
        self.items: dict[uuid.UUID, ReglaRating] = {}

    async def obtener(self, producto_id):
        return self.items.get(producto_id)

    async def guardar(self, regla):
        self.items[regla.producto_id] = regla

    async def invalidar(self, producto_id):
        self.items.pop(producto_id, None)


def _regla() -> ReglaRating:
    return ReglaRating(
        producto_id=uuid.uuid4(),
        version="1.0",
        definicion={},
        vigente_desde=datetime.now(timezone.utc),
    )


async def test_segunda_lectura_sale_de_cache():
    regla = _regla()
    repo, cache = RepoFalso([regla]), CacheFalso()
    resolver = ReglaRatingResolver(repo, cache)

    assert await resolver.obtener_vigente(regla.producto_id) == regla
    assert await resolver.obtener_vigente(regla.producto_id) == regla
    assert repo.consultas == 1


async def test_regla_inexistente_retorna_none_y_no_cachea():
    repo, cache = RepoFalso([]), CacheFalso()

    assert await ReglaRatingResolver(repo, cache).obtener_vigente(uuid.uuid4()) is None
    assert cache.items == {}


async def test_obtener_vigentes_combina_cache_y_bd():
    en_cache, en_bd = _regla(), _regla()
    repo, cache = RepoFalso([en_bd]), CacheFalso()
    await cache.guardar(en_cache)
    resolver = ReglaRatingResolver(repo, cache)

    reglas = await resolver.obtener_vigentes([en_cache.producto_id, en_bd.producto_id])

    assert set(reglas) == {en_cache.producto_id, en_bd.producto_id}
    assert en_bd.producto_id in cache.items
