import uuid
from dataclasses import asdict, fields

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.pagos.entities import Pago
from src.domain.pagos.repositories import PagoRepository
from src.infrastructure.persistence.models import PagoModel


class SqlAlchemyPagoRepository(PagoRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def guardar(self, pago: Pago) -> Pago:
        self.session.add(PagoModel(**asdict(pago)))
        await self.session.flush()
        return pago

    async def obtener_por_id(self, pago_id: uuid.UUID) -> Pago | None:
        model = await self.session.get(PagoModel, pago_id)
        if model is None:
            return None
        return Pago(**{field.name: getattr(model, field.name) for field in fields(Pago)})
