from dataclasses import dataclass, field
from typing import Any

from src.application.services.regla_rating_resolver import ReglaRatingResolver
from src.domain.productos.entities import Cobertura, EstadoProducto, ProductoSeguro
from src.domain.productos.repositories import (
    CoberturaRepository,
    ProductoSeguroRepository,
)


class ProductoNoEncontradoError(Exception):
    pass


@dataclass(frozen=True)
class ProductoCatalogo:
    producto: ProductoSeguro
    coberturas: list[Cobertura]
    moneda: str
    mensaje_legal: str
    fuentes_datos: list[str]
    parametros: list[dict[str, Any]] = field(default_factory=list)


class ConsultarCatalogoUseCase:
    def __init__(
        self,
        producto_repository: ProductoSeguroRepository,
        cobertura_repository: CoberturaRepository,
        regla_resolver: ReglaRatingResolver,
    ) -> None:
        self.producto_repository = producto_repository
        self.cobertura_repository = cobertura_repository
        self.regla_resolver = regla_resolver

    async def listar(self) -> list[ProductoCatalogo]:
        productos = await self.producto_repository.listar_activos()
        ids = [p.producto_id for p in productos]
        coberturas = await self.cobertura_repository.listar_activas_por_productos(ids)
        reglas = await self.regla_resolver.obtener_vigentes(ids)
        return [
            self._armar(p, coberturas.get(p.producto_id, []), reglas.get(p.producto_id))
            for p in productos
        ]

    async def obtener(self, codigo: str) -> ProductoCatalogo:
        producto = await self.producto_repository.obtener_por_codigo(codigo)
        if producto is None or producto.estado != EstadoProducto.ACTIVO:
            raise ProductoNoEncontradoError(codigo)
        coberturas = await self.cobertura_repository.listar_activas_por_producto(
            producto.producto_id
        )
        regla = await self.regla_resolver.obtener_vigente(producto.producto_id)
        return self._armar(producto, coberturas, regla)

    @staticmethod
    def _armar(producto, coberturas, regla) -> ProductoCatalogo:
        definicion = regla.definicion if regla is not None else {}
        return ProductoCatalogo(
            producto=producto,
            coberturas=coberturas,
            moneda=definicion.get("moneda", "COP"),
            mensaje_legal=definicion.get("mensaje_legal", ""),
            fuentes_datos=list(definicion.get("fuentes_datos", [])),
            parametros=list(definicion.get("parametros", [])),
        )
