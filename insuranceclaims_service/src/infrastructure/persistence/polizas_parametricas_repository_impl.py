from dataclasses import asdict, fields

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.siniestros.parametricos import PolizaParametrica
from src.domain.siniestros.repositories import PolizaParametricaRepository
from src.infrastructure.persistence.models import PolizaParametricaModel


def _a_entidad(modelo: PolizaParametricaModel) -> PolizaParametrica:
    return PolizaParametrica(**{campo.name: getattr(modelo, campo.name) for campo in fields(PolizaParametrica)})


class SqlAlchemyPolizaParametricaRepository(PolizaParametricaRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def guardar_o_actualizar(self, poliza: PolizaParametrica) -> PolizaParametrica:
        existente = await self.session.scalar(
            select(PolizaParametricaModel).where(
                PolizaParametricaModel.poliza_id == poliza.poliza_id,
                PolizaParametricaModel.cobertura == poliza.cobertura,
            )
        )
        if existente is None:
            self.session.add(PolizaParametricaModel(**asdict(poliza)))
        else:
            poliza.poliza_parametrica_id = existente.poliza_parametrica_id
            for campo, valor in asdict(poliza).items():
                setattr(existente, campo, valor)
        await self.session.flush()
        return poliza

    async def suscritas(self, cobertura: str, indice: str) -> list[PolizaParametrica]:
        modelos = await self.session.scalars(
            select(PolizaParametricaModel)
            .where(
                PolizaParametricaModel.cobertura == cobertura,
                PolizaParametricaModel.indice == indice,
                PolizaParametricaModel.activa.is_(True),
            )
            .order_by(PolizaParametricaModel.poliza_id)
        )
        return [_a_entidad(m) for m in modelos.all()]
