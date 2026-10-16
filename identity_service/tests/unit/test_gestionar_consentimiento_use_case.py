import uuid
from datetime import UTC, datetime

import pytest

from src.application.ports.consentimiento_cache import ConsentimientoCacheEntry
from src.application.use_cases.gestionar_consentimiento_use_case import (
    ConsentimientoNoOtorgadoError,
    GestionarConsentimientoUseCase,
)
from src.domain.clientes.entities import Cliente, ClienteId
from src.domain.consentimiento.entities import (
    ConsentimientoActual,
    EstadoConsentimiento,
)
from src.domain.consentimiento.repositories import ConsentimientoRepository
from src.infrastructure.cache.consentimiento_cache import ConsentimientoCache


class FakeConsentimientoRepository(ConsentimientoRepository):
    def __init__(self, estado: EstadoConsentimiento):
        self.actual = ConsentimientoActual(
            cliente_id=uuid.uuid4(),
            estado=estado,
            otorgado_en=datetime.now(UTC)
            if estado == EstadoConsentimiento.ACEPTADO
            else None,
            revocado_en=None,
        )
        self.lecturas = 0
        self.actualizaciones: list[
            tuple[uuid.UUID, EstadoConsentimiento, str, str]
        ] = []

    async def obtener_actual(self, cliente_id: uuid.UUID):
        self.lecturas += 1
        if self.actual.cliente_id != cliente_id:
            return None
        return self.actual

    async def actualizar_estado(
        self,
        cliente_id: uuid.UUID,
        estado: EstadoConsentimiento,
        version_terminos: str,
        canal: str,
    ):
        self.actualizaciones.append(
            (cliente_id, estado, version_terminos, canal)
        )
        self.actual = ConsentimientoActual(
            cliente_id=cliente_id,
            estado=estado,
            otorgado_en=(
                datetime.now(UTC)
                if estado == EstadoConsentimiento.ACEPTADO
                else self.actual.otorgado_en
            ),
            revocado_en=(
                datetime.now(UTC)
                if estado == EstadoConsentimiento.REVOCADO
                else None
            ),
        )
        return self.actual


class FakeRedis:
    def __init__(self):
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, ex: int):
        self.values[key] = value
        self.ttls[key] = ex

    async def delete(self, key: str):
        self.values.pop(key, None)

    async def aclose(self):
        pass


class FakeClienteRepository:
    def __init__(self, cliente: Cliente):
        self.cliente = cliente

    async def obtener_por_id(self, cliente_id: ClienteId):
        return self.cliente if self.cliente.id == cliente_id else None


def _cliente(cliente_id: uuid.UUID) -> Cliente:
    from datetime import date

    from src.domain.clientes.value_objects import EstadoKYC

    return Cliente(
        id=ClienteId(value=cliente_id),
        nombres="Ana",
        apellidos="Pérez",
        tipo_documento="CC",
        numero_identificacion="1020304050",
        correo="ana.perez@example.com",
        fecha_nacimiento=date(1990, 5, 15),
        pais_residencia="Colombia",
        telefono="+573001234567",
        estado_kyc=EstadoKYC.PENDIENTE,
    )


async def test_revocar_actualiza_redis_y_bloquea_perfil():
    repository = FakeConsentimientoRepository(EstadoConsentimiento.ACEPTADO)
    redis = FakeRedis()
    cache = ConsentimientoCache(redis)
    cliente_id = repository.actual.cliente_id
    use_case = GestionarConsentimientoUseCase(
        repository,
        FakeClienteRepository(_cliente(cliente_id)),
        cache,
        "2026-10",
    )

    revocado = await use_case.actualizar_consentimiento(
        cliente_id, EstadoConsentimiento.REVOCADO
    )

    assert revocado.estado == EstadoConsentimiento.REVOCADO
    assert repository.actualizaciones == [
        (cliente_id, EstadoConsentimiento.REVOCADO, "2026-10", "web")
    ]
    cached = await cache.obtener(cliente_id)
    assert cached.estado == EstadoConsentimiento.REVOCADO
    assert cached.perfil is None
    with pytest.raises(ConsentimientoNoOtorgadoError):
        await use_case.obtener_perfil_cliente(cliente_id)


async def test_reaceptar_consente_y_obtiene_perfil():
    repository = FakeConsentimientoRepository(EstadoConsentimiento.REVOCADO)
    cache = ConsentimientoCache(FakeRedis())
    cliente_id = repository.actual.cliente_id
    use_case = GestionarConsentimientoUseCase(
        repository,
        FakeClienteRepository(_cliente(cliente_id)),
        cache,
        "2026-10",
    )

    await use_case.actualizar_consentimiento(
        cliente_id, EstadoConsentimiento.ACEPTADO
    )
    perfil = await use_case.obtener_perfil_cliente(cliente_id)

    assert perfil["correo"] == "ana.perez@example.com"
    assert (await cache.obtener(cliente_id)).estado == EstadoConsentimiento.ACEPTADO


async def test_cache_redis_guarda_perfil_y_consentimiento_con_ttl_maximo():
    redis = FakeRedis()
    cache = ConsentimientoCache(redis, ttl_seconds=301)
    cliente_id = uuid.uuid4()
    perfil = {"nombres": "Ana"}
    await cache.guardar(cliente_id, EstadoConsentimiento.ACEPTADO, perfil)

    assert cache.ttl_seconds == 300
    assert redis.ttls[cache._key(cliente_id)] == 300
    entry = await cache.obtener(cliente_id)
    assert entry == ConsentimientoCacheEntry(
        estado=EstadoConsentimiento.ACEPTADO,
        perfil=perfil,
    )