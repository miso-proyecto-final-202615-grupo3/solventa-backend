import uuid

from redis.exceptions import RedisError

from src.application.ports.perfil_cliente_gateway import (
    PerfilCliente,
    PerfilClienteGateway,
)


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
        )
