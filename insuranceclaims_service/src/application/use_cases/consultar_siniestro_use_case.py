import uuid

from src.domain.siniestros.entities import Siniestro
from src.domain.siniestros.errores import SiniestroNoEncontrado
from src.domain.siniestros.repositories import SiniestroRepository


class ConsultarSiniestroUseCase:
    """Un siniestro del cliente; uno ajeno responde igual que uno inexistente (404 uniforme)."""

    def __init__(self, repo: SiniestroRepository) -> None:
        self.repo = repo

    async def ejecutar(self, siniestro_id: uuid.UUID, cliente_id: uuid.UUID) -> Siniestro:
        siniestro = await self.repo.obtener_de_cliente(siniestro_id, cliente_id)
        if siniestro is None:
            raise SiniestroNoEncontrado()
        return siniestro
