import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.pagos.entities import EstadoPago, MetodoPago, PagoPrima
from src.domain.pagos.repositories import PagoDuplicadoError
from src.infrastructure.persistence.models import EventoOutboxModel, PagoPrimaModel
from src.infrastructure.persistence.pago_prima_repository_impl import SqlAlchemyPagoPrimaRepository

AHORA = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)


def nuevo_pago(
    cotizacion_id: uuid.UUID | None = None,
    cliente_id: uuid.UUID | None = None,
    clave: str = "clave-1",
    estado: EstadoPago = EstadoPago.PENDIENTE,
) -> PagoPrima:
    return PagoPrima(
        cotizacion_id=cotizacion_id or uuid.uuid4(),
        cliente_id=cliente_id or uuid.uuid4(),
        monto=Decimal("1250000.50"),
        moneda="COP",
        metodo_pago=MetodoPago.TARJETA_CREDITO,
        proveedor="mock_paymentprovider",
        idempotency_key=clave,
        hash_solicitud="a" * 64,
        correlation_id="corr-1",
        creado_en=AHORA,
        actualizado_en=AHORA,
        estado=estado,
    )


async def test_guarda_y_recupera_un_pago(db_session: AsyncSession):
    repo = SqlAlchemyPagoPrimaRepository(db_session)
    pago = nuevo_pago()

    await repo.crear(pago)
    await db_session.commit()
    db_session.expunge_all()

    assert await repo.obtener_por_id(pago.pago_id) == pago
    assert await repo.obtener_por_idempotency_key(pago.cliente_id, "clave-1") == pago
    assert await repo.obtener_por_idempotency_key(uuid.uuid4(), "clave-1") is None
    assert await repo.obtener_por_idempotency_key(pago.cliente_id, "otra") is None
    assert await repo.obtener_por_id(uuid.uuid4()) is None


async def test_la_clave_de_idempotencia_es_unica_por_cliente(db_session: AsyncSession):
    repo = SqlAlchemyPagoPrimaRepository(db_session)
    cliente = uuid.uuid4()
    await repo.crear(nuevo_pago(cliente_id=cliente))
    await db_session.commit()

    with pytest.raises(PagoDuplicadoError):
        await repo.crear(nuevo_pago(cliente_id=cliente))
    await db_session.rollback()

    await repo.crear(nuevo_pago())  # otro cliente puede usar la misma clave


@pytest.mark.parametrize("estado", [EstadoPago.PENDIENTE, EstadoPago.APROBADO, EstadoPago.ERROR])
async def test_un_solo_pago_activo_por_cotizacion(db_session: AsyncSession, estado):
    repo = SqlAlchemyPagoPrimaRepository(db_session)
    cotizacion = uuid.uuid4()
    activo = nuevo_pago(cotizacion, estado=estado)
    await repo.crear(activo)
    await db_session.commit()

    assert (await repo.obtener_activo_por_cotizacion(cotizacion)).pago_id == activo.pago_id
    with pytest.raises(PagoDuplicadoError):
        await repo.crear(nuevo_pago(cotizacion, clave="clave-2"))
    await db_session.rollback()


async def test_un_pago_rechazado_no_bloquea_otro_intento(db_session: AsyncSession):
    repo = SqlAlchemyPagoPrimaRepository(db_session)
    cotizacion = uuid.uuid4()
    await repo.crear(nuevo_pago(cotizacion, estado=EstadoPago.RECHAZADO))
    await db_session.commit()

    assert await repo.obtener_activo_por_cotizacion(cotizacion) is None
    await repo.crear(nuevo_pago(cotizacion, clave="clave-2"))
    await repo.crear(nuevo_pago(cotizacion, clave="clave-3", estado=EstadoPago.RECHAZADO))


async def test_actualizar_usa_control_optimista_de_version(db_session: AsyncSession):
    repo = SqlAlchemyPagoPrimaRepository(db_session)
    pago = nuevo_pago()
    await repo.crear(pago)
    await db_session.commit()
    obsoleto = await repo.obtener_por_id(pago.pago_id)

    pago.estado = EstadoPago.APROBADO
    pago.proveedor_referencia = "PAYPAL_1"
    pago.procesado_en = AHORA + timedelta(seconds=3)
    assert await repo.actualizar(pago) is True
    assert pago.version == 2
    await db_session.commit()

    obsoleto.estado = EstadoPago.RECHAZADO
    assert await repo.actualizar(obsoleto) is False
    assert obsoleto.version == 1
    guardado = await repo.obtener_por_id(pago.pago_id)
    assert guardado == pago
    assert (guardado.estado, guardado.proveedor_referencia) == (EstadoPago.APROBADO, "PAYPAL_1")
    assert guardado.procesado_en == AHORA + timedelta(seconds=3)


async def test_crear_no_confirma_la_transaccion(db_session: AsyncSession):
    repo = SqlAlchemyPagoPrimaRepository(db_session)
    pago = nuevo_pago()
    await repo.crear(pago)

    await db_session.rollback()

    assert await repo.obtener_por_id(pago.pago_id) is None


def test_el_modelo_no_guarda_datos_sensibles_de_la_tarjeta():
    columnas = set(PagoPrimaModel.__table__.columns.keys())

    assert {"tarjeta_ultimos4", "tarjeta_marca", "hash_solicitud", "idempotency_key"} <= columnas
    assert not columnas & {
        "numero_tarjeta", "tarjeta_numero", "cvv", "pan", "tarjeta_token", "paypal_email",
        "mes_expiracion", "anio_expiracion",
    }
    assert PagoPrimaModel.__table__.schema == "payments"
    assert EventoOutboxModel.__table__.schema == "payments"
    assert PagoPrimaModel.__table__.c.monto.type.scale == 2
