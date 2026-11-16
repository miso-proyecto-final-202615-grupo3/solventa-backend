import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.productos.entities import EstadoProducto, ProductoSeguro
from src.domain.productos.producto_seguro_repository import ProductoSeguroRepository
from src.infrastructure.persistence.models import ProductoSeguroModel


def _a_entidad(model: ProductoSeguroModel) -> ProductoSeguro:
    return ProductoSeguro(
        producto_id=model.producto_id,
        codigo=model.codigo,
        nombre=model.nombre,
        ramo=model.ramo,
        estado=EstadoProducto(model.estado),
        pais=model.pais,
        condiciones_generales=model.condiciones_generales,
        version_condiciones_generales=model.version_condiciones_generales,
    )


class SqlAlchemyProductoSeguroRepository(ProductoSeguroRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def guardar(self, producto: ProductoSeguro) -> ProductoSeguro:
        self.session.add(
            ProductoSeguroModel(
                producto_id=producto.producto_id,
                codigo=producto.codigo,
                nombre=producto.nombre,
                ramo=producto.ramo,
                estado=producto.estado.value,
                pais=producto.pais,
                condiciones_generales=producto.condiciones_generales,
                version_condiciones_generales=producto.version_condiciones_generales,
            )
        )
        await self.session.flush()
        return producto

    async def inicializar_condiciones(
        self, producto_id: uuid.UUID, condiciones: str, version: str
    ) -> None:
        model = await self.session.get(ProductoSeguroModel, producto_id)
        if model is None:
            raise ValueError(f"Producto no encontrado: {producto_id}")
        if model.condiciones_generales is None and model.version_condiciones_generales is None:
            model.condiciones_generales = condiciones
            model.version_condiciones_generales = version
            await self.session.flush()

    async def obtener_por_id(self, producto_id: uuid.UUID) -> ProductoSeguro | None:
        model = await self.session.get(ProductoSeguroModel, producto_id)
        return _a_entidad(model) if model else None

    async def obtener_por_codigo(self, codigo: str) -> ProductoSeguro | None:
        result = await self.session.execute(
            select(ProductoSeguroModel).where(ProductoSeguroModel.codigo == codigo)
        )
        model = result.scalar_one_or_none()
        return _a_entidad(model) if model else None

    async def listar_activos(self) -> list[ProductoSeguro]:
        result = await self.session.execute(
            select(ProductoSeguroModel)
            .where(ProductoSeguroModel.estado == EstadoProducto.ACTIVO.value)
            .order_by(ProductoSeguroModel.nombre)
        )
        return [_a_entidad(m) for m in result.scalars().all()]
