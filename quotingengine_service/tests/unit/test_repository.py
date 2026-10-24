import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.persistence.models import (
    AuditoriaDecisionModel,
    CoberturaModel,
    CotizacionCoberturaModel,
    CotizacionModel,
    ProductoSeguroModel,
    ReglaRatingModel,
)
from src.infrastructure.persistence.repository import (
    AuditoriaDecisionRepository,
    CoberturaRepository,
    CotizacionCoberturaRepository,
    CotizacionRepository,
    ProductoSeguroRepository,
    ReglaRatingRepository,
)


async def test_flujo_completo_de_cotizacion(db_session: AsyncSession):
    ahora = datetime.now(timezone.utc)
    productos = ProductoSeguroRepository(db_session)
    coberturas = CoberturaRepository(db_session)
    reglas = ReglaRatingRepository(db_session)
    cotizaciones = CotizacionRepository(db_session)
    detalles = CotizacionCoberturaRepository(db_session)
    auditorias = AuditoriaDecisionRepository(db_session)

    producto = await productos.add(
        ProductoSeguroModel(
            codigo="VIDA-01", nombre="Vida", ramo="VIDA", estado="ACTIVO", pais="CO"
        )
    )
    cobertura = await coberturas.add(
        CoberturaModel(
            producto_id=producto.producto_id,
            codigo="MUERTE",
            nombre="Muerte",
            limite_asegurado=Decimal("1000000"),
            deducible=Decimal("0"),
            estado="ACTIVA",
        )
    )
    regla = await reglas.add(
        ReglaRatingModel(
            producto_id=producto.producto_id,
            version="1.0",
            estado="VIGENTE",
            definicion={"base": 10},
            vigente_desde=ahora,
        )
    )
    cliente_id = uuid.uuid4()
    cotizacion = await cotizaciones.add(
        CotizacionModel(
            cliente_id=cliente_id,
            producto_id=producto.producto_id,
            estado="EMITIDA",
            prima_total=Decimal("50.00"),
            moneda="COP",
            expira_en=ahora + timedelta(days=1),
        )
    )
    await detalles.add(
        CotizacionCoberturaModel(
            cotizacion_id=cotizacion.cotizacion_id,
            cobertura_id=cobertura.cobertura_id,
            prima=Decimal("50.00"),
            limite_asegurado=Decimal("1000000"),
            deducible=Decimal("0"),
        )
    )
    await auditorias.add(
        AuditoriaDecisionModel(
            cotizacion_id=cotizacion.cotizacion_id,
            regla_rating_id=regla.regla_rating_id,
            tipo_decision="RATING",
            entradas={"edad": 30},
            resultado={"prima": "50.00"},
        )
    )

    assert (await productos.get_by_codigo("VIDA-01")).producto_id == producto.producto_id
    assert len(await coberturas.list_by_producto(producto.producto_id)) == 1
    assert len(await reglas.list_by_producto(producto.producto_id)) == 1
    assert len(await cotizaciones.list_by_cliente(cliente_id)) == 1
    assert len(await detalles.list_by_cotizacion(cotizacion.cotizacion_id)) == 1
    assert len(await auditorias.list_by_cotizacion(cotizacion.cotizacion_id)) == 1
