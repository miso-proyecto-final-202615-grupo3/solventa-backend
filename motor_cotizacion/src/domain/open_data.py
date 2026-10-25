from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class CategoriaOpenData(StrEnum):
    BAJO_RIESGO = "BAJO_RIESGO"
    ESTANDAR = "ESTANDAR"
    RIESGO_ELEVADO = "RIESGO_ELEVADO"

    @property
    def factor(self) -> Decimal:
        return {
            CategoriaOpenData.BAJO_RIESGO: Decimal("0.95"),
            CategoriaOpenData.ESTANDAR: Decimal("1.00"),
            CategoriaOpenData.RIESGO_ELEVADO: Decimal("1.10"),
        }[self]


@dataclass(frozen=True)
class PerfilTerritorial:
    categoria: CategoriaOpenData
    id_territorial: Decimal
    ir_publico: Decimal
