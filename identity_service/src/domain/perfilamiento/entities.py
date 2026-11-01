from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class PerfilOpenFinance:
    ingreso_mensual: Decimal
    ahorros_liquidos: Decimal
    dti_pct: Decimal
    sobregiros_12_meses: int
    score: int
