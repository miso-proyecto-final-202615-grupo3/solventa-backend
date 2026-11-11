import uuid

from src.domain.firmas.entities import FirmaDigital
from src.domain.firmas.repositories import FirmaDigitalRepository


class FirmaNoEncontradaError(Exception):
    pass


class ConsultarFirmaDigitalUseCase:
    def __init__(self, firmas: FirmaDigitalRepository) -> None:
        self.firmas = firmas

    async def ejecutar(self, cotizacion_id: uuid.UUID) -> FirmaDigital:
        firma = await self.firmas.obtener_activa_por_cotizacion(cotizacion_id)
        if firma is None:
            raise FirmaNoEncontradaError("La cotización no tiene una firma digital vigente.")
        return firma
