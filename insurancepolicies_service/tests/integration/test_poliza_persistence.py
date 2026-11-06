import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.polizas.entities import Poliza, PolizaCobertura
from src.infrastructure.persistence.poliza_repository_impl import (
    SqlAlchemyPolizaRepository,
)


def _poliza(
    cliente_id: uuid.UUID | None = None,
    numero: str = "POL-0001",
    desde: datetime | None = None,
) -> Poliza:
    desde = desde or datetime(2026, 1, 1, tzinfo=UTC)
    poliza = Poliza(
        cliente_id=cliente_id or uuid.uuid4(),
        cotizacion_id=uuid.uuid4(),
        producto_id=uuid.uuid4(),
        numero=numero,
        estado="EMITIDA",
        vigencia_desde=desde,
        vigencia_hasta=desde + timedelta(days=365),
        emitida_en=desde,
    )
    poliza.coberturas = [
        PolizaCobertura(
            poliza_id=poliza.poliza_id,
            cobertura_id=uuid.uuid4(),
            limite_asegurado=Decimal("1000000.00"),
            deducible=Decimal("50000.00"),
            prima=Decimal("12000.50"),
        ),
        PolizaCobertura(
            poliza_id=poliza.poliza_id,
            cobertura_id=uuid.uuid4(),
            limite_asegurado=Decimal("500000.00"),
            deducible=Decimal("0.00"),
            prima=Decimal("3000.00"),
        ),
    ]
    return poliza


async def test_guarda_y_obtiene_poliza_con_coberturas(db_session: AsyncSession):
    repo = SqlAlchemyPolizaRepository(db_session)
    poliza = _poliza()

    await repo.guardar(poliza)
    await db_session.commit()
    encontrada = await repo.obtener_por_id(poliza.poliza_id)

    assert encontrada is not None
    assert encontrada.numero == "POL-0001"
    assert encontrada.cliente_id == poliza.cliente_id
    assert {c.cobertura_id for c in encontrada.coberturas} == {
        c.cobertura_id for c in poliza.coberturas
    }
    assert sum(c.prima for c in encontrada.coberturas) == Decimal("15000.50")


async def test_obtener_inexistente_retorna_none(db_session: AsyncSession):
    repo = SqlAlchemyPolizaRepository(db_session)

    assert await repo.obtener_por_id(uuid.uuid4()) is None
    assert await repo.obtener_por_numero("NO-EXISTE") is None


async def test_obtiene_por_numero(db_session: AsyncSession):
    repo = SqlAlchemyPolizaRepository(db_session)
    poliza = _poliza(numero="POL-0042")
    await repo.guardar(poliza)

    encontrada = await repo.obtener_por_numero("POL-0042")

    assert encontrada is not None
    assert encontrada.poliza_id == poliza.poliza_id


async def test_lista_por_cliente(db_session: AsyncSession):
    repo = SqlAlchemyPolizaRepository(db_session)
    cliente_id = uuid.uuid4()
    await repo.guardar(
        _poliza(cliente_id, "POL-A", datetime(2026, 1, 1, tzinfo=UTC))
    )
    await repo.guardar(
        _poliza(cliente_id, "POL-B", datetime(2027, 1, 1, tzinfo=UTC))
    )
    await repo.guardar(_poliza(numero="POL-OTRO"))

    polizas = await repo.listar_por_cliente(cliente_id)

    assert [p.numero for p in polizas] == ["POL-B", "POL-A"]


async def test_numero_de_poliza_es_unico(db_session: AsyncSession):
    repo = SqlAlchemyPolizaRepository(db_session)
    await repo.guardar(_poliza(numero="POL-DUP"))

    with pytest.raises(IntegrityError):
        await repo.guardar(_poliza(numero="POL-DUP"))
