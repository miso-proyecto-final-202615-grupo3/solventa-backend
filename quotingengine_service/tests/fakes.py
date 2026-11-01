import uuid
from decimal import Decimal

from redis.exceptions import RedisError

from src.application.ports.perfil_cliente_gateway import (
    PerfilCliente,
    PerfilClienteGateway,
)
from src.application.ports.open_data_gateway import OpenDataNoDisponibleError
from src.domain.open_data import CategoriaOpenData, PerfilTerritorial


class FakeRedis:
    def __init__(self, fallar: bool = False) -> None:
        self.data: dict[str, str] = {}
        self.ttls: dict[str, int | None] = {}
        self.fallar = fallar

    def _check(self) -> None:
        if self.fallar:
            raise RedisError("redis caído")

    async def get(self, key: str):
        self._check()
        return self.data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        self._check()
        self.data[key] = value
        self.ttls[key] = ex

    async def delete(self, key: str):
        self._check()
        self.data.pop(key, None)

    async def aclose(self) -> None:
        pass


class FakePerfilGateway(PerfilClienteGateway):
    """Devuelve un perfil o lanza la excepción configurada."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.llamadas: list[uuid.UUID] = []

    async def obtener_perfil(self, cliente_id: uuid.UUID) -> PerfilCliente:
        self.llamadas.append(cliente_id)
        if self.error is not None:
            raise self.error
        return PerfilCliente(
            cliente_id=cliente_id,
            nombres="Ana",
            apellidos="Pérez",
            tipo_documento="CC",
            numero_identificacion="123",
            correo="ana@example.com",
            fecha_nacimiento=None,
            pais_residencia="CO",
            telefono="3000000000",
            estado_kyc="VALIDADO",
            ingreso_mensual=Decimal("8500000"),
            ahorros_liquidos=Decimal("25500000"),
            dti_pct=Decimal("28"),
            sobregiros_12_meses=0,
            score=820,
        )


class FakeOpenDataGateway:
    def __init__(self, categoria=CategoriaOpenData.BAJO_RIESGO, error=None):
        self.categoria = categoria
        self.error = error
        self.ubicaciones: list[dict] = []

    async def obtener_riesgo(self, ubicacion):
        self.ubicaciones.append(ubicacion)
        if self.error is not None:
            raise self.error
        return PerfilTerritorial(self.categoria)
