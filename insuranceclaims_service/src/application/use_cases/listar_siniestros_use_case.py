"""Siniestros del cliente, opcionalmente de una póliza (HU4.2.1, decisiones C1–C3)."""
import uuid
from dataclasses import dataclass

from src.domain.siniestros.entities import Siniestro
from src.domain.siniestros.repositories import SiniestroRepository

TAMANO_MAX = 50


@dataclass(frozen=True)
class PaginaSiniestros:
    siniestros: list[Siniestro]
    pagina: int
    tamano: int
    total: int


class ListarSiniestrosUseCase:
    """El dueño viene del token: un `poliza_id` de otro cliente simplemente no trae resultados."""

    def __init__(self, repo: SiniestroRepository) -> None:
        self.repo = repo

    async def ejecutar(
        self, cliente_id: uuid.UUID, poliza_id: uuid.UUID | None, pagina: int, tamano: int
    ) -> PaginaSiniestros:
        if pagina < 1 or not 1 <= tamano <= TAMANO_MAX:
            raise ValueError("pagina debe ser >= 1 y tamano entre 1 y 50")
        siniestros, total = await self.repo.listar_de_cliente(cliente_id, poliza_id, tamano, (pagina - 1) * tamano)
        return PaginaSiniestros(siniestros, pagina, tamano, total)
