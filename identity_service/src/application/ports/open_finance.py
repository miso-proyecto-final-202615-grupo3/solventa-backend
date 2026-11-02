from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
import uuid


class OpenFinanceNoDisponibleError(Exception):
    pass


@dataclass(frozen=True)
class PerfilOpenFinance:
    ingreso_mensual: Decimal
    ahorros_liquidos: Decimal
    dti_pct: Decimal
    sobregiros_12_meses: int
    score: int


class OpenFinanceGateway(ABC):
    @abstractmethod
    async def obtener_perfil(self, cliente_id: uuid.UUID) -> PerfilOpenFinance:
        raise NotImplementedError
