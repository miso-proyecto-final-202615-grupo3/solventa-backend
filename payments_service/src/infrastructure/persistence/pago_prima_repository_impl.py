import uuid
from dataclasses import fields
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.pagos.entities import ESTADOS_PAGO_ACTIVO, EstadoPago, MetodoPago, PagoPrima
from src.domain.pagos.repositories import PagoDuplicadoError, PagoPrimaRepository
from src.infrastructure.persistence.models import PagoPrimaModel

_CAMPOS = [f.name for f in fields(PagoPrima)]
_ACTUALIZABLES = [c for c in _CAMPOS if c not in ("pago_id", "version")]


def _con_zona(valor: datetime | None) -> datetime | None:
    # SQLite devuelve fechas sin zona horaria; PostgreSQL las devuelve en UTC.
    if valor is not None and valor.tzinfo is None:
        return valor.replace(tzinfo=UTC)
    return valor


def _a_entidad(model: PagoPrimaModel | None) -> PagoPrima | None:
    if model is None:
        return None
    valores = {campo: getattr(model, campo) for campo in _CAMPOS}
    valores["estado"] = EstadoPago(valores["estado"])
    valores["metodo_pago"] = MetodoPago(valores["metodo_pago"])
    for campo in ("creado_en", "actualizado_en", "procesado_en"):
        valores[campo] = _con_zona(valores[campo])
    return PagoPrima(**valores)


def _a_valores(pago: PagoPrima) -> dict:
    valores = {campo: getattr(pago, campo) for campo in _ACTUALIZABLES}
    valores["estado"] = pago.estado.value
    valores["metodo_pago"] = pago.metodo_pago.value
    return valores


class SqlAlchemyPagoPrimaRepository(PagoPrimaRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def crear(self, pago: PagoPrima) -> None:
        self.session.add(
            PagoPrimaModel(pago_id=pago.pago_id, version=pago.version, **_a_valores(pago))
        )
        try:
            await self.session.flush()
        except IntegrityError as exc:
            raise PagoDuplicadoError() from exc

    async def obtener_por_id(self, pago_id: uuid.UUID) -> PagoPrima | None:
        result = await self.session.execute(
            select(PagoPrimaModel)
            .where(PagoPrimaModel.pago_id == pago_id)
            .execution_options(populate_existing=True)
        )
        return _a_entidad(result.scalar_one_or_none())

    async def obtener_por_idempotency_key(
        self, cliente_id: uuid.UUID, idempotency_key: str
    ) -> PagoPrima | None:
        result = await self.session.execute(
            select(PagoPrimaModel)
            .where(
                PagoPrimaModel.cliente_id == cliente_id,
                PagoPrimaModel.idempotency_key == idempotency_key,
            )
            .execution_options(populate_existing=True)
        )
        return _a_entidad(result.scalar_one_or_none())

    async def obtener_activo_por_cotizacion(self, cotizacion_id: uuid.UUID) -> PagoPrima | None:
        result = await self.session.execute(
            select(PagoPrimaModel)
            .where(
                PagoPrimaModel.cotizacion_id == cotizacion_id,
                PagoPrimaModel.estado.in_([e.value for e in ESTADOS_PAGO_ACTIVO]),
            )
            .execution_options(populate_existing=True)
        )
        return _a_entidad(result.scalar_one_or_none())

    async def actualizar(self, pago: PagoPrima) -> bool:
        result = await self.session.execute(
            update(PagoPrimaModel)
            .where(
                PagoPrimaModel.pago_id == pago.pago_id,
                PagoPrimaModel.version == pago.version,
            )
            .values(**_a_valores(pago), version=pago.version + 1)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            return False
        pago.version += 1
        return True
