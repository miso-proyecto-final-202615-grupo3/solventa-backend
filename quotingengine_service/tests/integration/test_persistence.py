import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.auditoria.entities import AuditoriaDecision
from src.domain.cotizaciones.entities import Cotizacion, CotizacionCobertura
from src.domain.productos.entities import Cobertura, ProductoSeguro
from src.domain.reglas_rating.entities import ReglaRating
from src.infrastructure.persistence.auditoria_decision_repository_impl import (
    SqlAlchemyAuditoriaDecisionRepository,
)
from src.infrastructure.persistence.cobertura_repository_impl import (
    SqlAlchemyCoberturaRepository,
)
from src.infrastructure.persistence.cotizacion_cobertura_repository_impl import (
    SqlAlchemyCotizacionCoberturaRepository,
)
from src.infrastructure.persistence.cotizacion_repository_impl import (
    SqlAlchemyCotizacionRepository,
)
from src.infrastructure.persistence.producto_seguro_repository_impl import (
    SqlAlchemyProductoSeguroRepository,
)
from src.infrastructure.persistence.regla_rating_repository_impl import (
    SqlAlchemyReglaRatingRepository,
)


async def test_flujo_completo_de_persistencia(db_session: AsyncSession):
    ahora = datetime.now(timezone.utc)
    productos = SqlAlchemyProductoSeguroRepository(db_session)
    coberturas = SqlAlchemyCoberturaRepository(db_session)
    reglas = SqlAlchemyReglaRatingRepository(db_session)
    cotizaciones = SqlAlchemyCotizacionRepository(db_session)
    detalles = SqlAlchemyCotizacionCoberturaRepository(db_session)
    auditorias = SqlAlchemyAuditoriaDecisionRepository(db_session)

    producto = await productos.guardar(
        ProductoSeguro(codigo="VIDA-01", nombre="Vida", ramo="VIDA", pais="CO")
    )
    cobertura = await coberturas.guardar(
        Cobertura(
            producto_id=producto.producto_id,
            codigo="MUERTE",
            nombre="Muerte",
            limite_asegurado=Decimal("1000000"),
            deducible=Decimal("0"),
        )
    )
    regla = await reglas.guardar(
        ReglaRating(
            producto_id=producto.producto_id,
            version="1.0",
            definicion={"tasa_base": "0.1"},
            vigente_desde=ahora - timedelta(minutes=1),
        )
    )
    cliente_id = uuid.uuid4()
    cotizacion = await cotizaciones.guardar(
        Cotizacion(
            cliente_id=cliente_id,
            producto_id=producto.producto_id,
            prima_total=Decimal("50.00"),
            moneda="COP",
            expira_en=ahora + timedelta(days=1),
        )
    )
    await detalles.guardar_todas(
        [
            CotizacionCobertura(
                cotizacion_id=cotizacion.cotizacion_id,
                cobertura_id=cobertura.cobertura_id,
                prima=Decimal("50.00"),
                limite_asegurado=Decimal("1000000"),
                deducible=Decimal("0"),
            )
        ]
    )
    await auditorias.guardar(
        AuditoriaDecision(
            cotizacion_id=cotizacion.cotizacion_id,
            regla_rating_id=regla.regla_rating_id,
            tipo_decision="RATING",
            entradas={"monto": "1"},
            resultado={"prima_total": "50.00"},
        )
    )

    assert (await productos.obtener_por_codigo("VIDA-01")).producto_id == producto.producto_id
    assert (await productos.obtener_por_id(producto.producto_id)).nombre == "Vida"
    assert [p.codigo for p in await productos.listar_activos()] == ["VIDA-01"]
    assert len(await coberturas.listar_activas_por_producto(producto.producto_id)) == 1
    vigente = await reglas.obtener_vigente_por_producto(producto.producto_id)
    assert vigente.regla_rating_id == regla.regla_rating_id
    assert await reglas.existe_por_producto(producto.producto_id)
    assert cotizacion.creada_en is not None
    assert len(await cotizaciones.listar_por_cliente(cliente_id)) == 1
    assert (await cotizaciones.obtener_por_id(cotizacion.cotizacion_id)).prima_total == Decimal("50.00")
    assert len(await detalles.listar_por_cotizacion(cotizacion.cotizacion_id)) == 1
    assert len(await auditorias.listar_por_cotizacion(cotizacion.cotizacion_id)) == 1


async def test_regla_vencida_o_obsoleta_no_es_vigente(db_session: AsyncSession):
    ahora = datetime.now(timezone.utc)
    productos = SqlAlchemyProductoSeguroRepository(db_session)
    reglas = SqlAlchemyReglaRatingRepository(db_session)
    producto = await productos.guardar(
        ProductoSeguro(codigo="X", nombre="X", ramo="X", pais="CO")
    )
    await reglas.guardar(
        ReglaRating(
            producto_id=producto.producto_id,
            version="0.9",
            definicion={},
            vigente_desde=ahora - timedelta(days=10),
            vigente_hasta=ahora - timedelta(days=1),
        )
    )

    assert await reglas.obtener_vigente_por_producto(producto.producto_id) is None
    assert await reglas.obtener_vigentes_por_productos([]) == {}
