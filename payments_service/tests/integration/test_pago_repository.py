import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.pagos.entities import Pago
from src.infrastructure.persistence.models import PagoModel
from src.infrastructure.persistence.pagos_repository_impl import SqlAlchemyPagoRepository


def nuevo_pago(clave: str = "pago-123") -> Pago:
    return Pago(
        poliza_id=uuid.uuid4(),
        indemnizacion_id=uuid.uuid4(),
        tipo="indemnizacion",
        monto=Decimal("12345.67"),
        moneda="COP",
        estado="procesado",
        clave_idempotencia=clave,
        procesado_en=datetime(2026, 1, 2, 12, 30, tzinfo=timezone.utc),
    )


async def test_guardar_y_recuperar_pago(db_session: AsyncSession):
    repository = SqlAlchemyPagoRepository(db_session)
    pago = nuevo_pago()
    assert await repository.guardar(pago) == pago
    await db_session.commit()
    db_session.expunge_all()

    recuperado = await repository.obtener_por_id(pago.pago_id)
    assert recuperado is not None
    assert recuperado.pago_id == pago.pago_id
    assert recuperado.poliza_id == pago.poliza_id
    assert recuperado.indemnizacion_id == pago.indemnizacion_id
    assert recuperado.tipo == pago.tipo
    assert recuperado.monto == pago.monto
    assert recuperado.moneda == pago.moneda
    assert recuperado.estado == pago.estado
    assert recuperado.clave_idempotencia == pago.clave_idempotencia
    assert recuperado.procesado_en is not None
    assert recuperado.procesado_en.replace(tzinfo=timezone.utc) == pago.procesado_en
    assert await repository.obtener_por_id(uuid.uuid4()) is None


async def test_campo_opcional_y_clave_idempotencia_unica(db_session: AsyncSession):
    repository = SqlAlchemyPagoRepository(db_session)
    pago = nuevo_pago()
    pago.indemnizacion_id = None
    pago.procesado_en = None
    await repository.guardar(pago)
    await db_session.commit()
    db_session.expunge_all()
    assert await repository.obtener_por_id(pago.pago_id) == pago

    with pytest.raises(IntegrityError):
        await repository.guardar(nuevo_pago(pago.clave_idempotencia))
    await db_session.rollback()


async def test_guardar_no_confirma_la_transaccion(db_session: AsyncSession):
    repository = SqlAlchemyPagoRepository(db_session)
    pago = nuevo_pago()
    await repository.guardar(pago)
    await db_session.rollback()
    assert await repository.obtener_por_id(pago.pago_id) is None


def test_modelo_corresponde_a_especificacion():
    table = PagoModel.__table__
    assert table.schema == "payments"
    assert set(table.columns.keys()) == {
        "pago_id", "poliza_id", "indemnizacion_id", "tipo", "monto",
        "moneda", "estado", "clave_idempotencia", "procesado_en",
    }
    assert {column.name for column in table.primary_key} == {"pago_id"}
    assert table.c.clave_idempotencia.unique
    assert (table.c.monto.type.precision, table.c.monto.type.scale) == (18, 2)
    assert table.c.procesado_en.type.timezone
    assert not table.foreign_keys
