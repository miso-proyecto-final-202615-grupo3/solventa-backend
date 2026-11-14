import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime

from src.application.ports.polizas import PolizaResumen, PolizasNoDisponibles, PolizasPort
from src.domain.siniestros.catalogo import IDIOMA_POR_DEFECTO, CatalogoTiposSiniestro, TipoSiniestro
from src.domain.siniestros.errores import ServicioNoDisponible


@dataclass(frozen=True)
class PolizaElegible:
    poliza: PolizaResumen
    tipos: list[TipoSiniestro]


def poliza_en_estado_elegible(poliza: PolizaResumen, estados_elegibles: Iterable[str]) -> bool:
    return poliza.estado.upper() in {estado.strip().upper() for estado in estados_elegibles}


def dia_en_vigencia(poliza: PolizaResumen, dia: date) -> bool:
    return poliza.vigencia_desde <= dia <= poliza.vigencia_hasta


class ListarPolizasElegiblesUseCase:
    """Pólizas vigentes del cliente cuyo producto admite reportes desde la app (CA1 de HU4.1.1)."""

    def __init__(
        self,
        polizas: PolizasPort,
        catalogo: CatalogoTiposSiniestro,
        reloj: Callable[[], datetime],
        estados_elegibles: Iterable[str],
    ) -> None:
        self.polizas = polizas
        self.catalogo = catalogo
        self.reloj = reloj
        self.estados_elegibles = tuple(estados_elegibles)

    async def ejecutar(
        self, cliente_id: uuid.UUID, correlation_id: str, idioma: str = IDIOMA_POR_DEFECTO
    ) -> list[PolizaElegible]:
        try:
            polizas = await self.polizas.listar_por_cliente(cliente_id, correlation_id)
        except PolizasNoDisponibles as exc:
            raise ServicioNoDisponible() from exc

        hoy = self.reloj().date()
        elegibles = []
        for poliza in polizas:
            if poliza.cliente_id != cliente_id:
                continue
            if not poliza_en_estado_elegible(poliza, self.estados_elegibles) or not dia_en_vigencia(poliza, hoy):
                continue
            tipos = await self.catalogo.tipos_de(poliza.producto_codigo, idioma)
            if tipos:
                elegibles.append(PolizaElegible(poliza, tipos))
        return sorted(elegibles, key=lambda e: e.poliza.vigencia_hasta, reverse=True)
