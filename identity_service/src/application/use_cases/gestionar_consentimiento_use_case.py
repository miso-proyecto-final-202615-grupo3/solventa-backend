import uuid
from datetime import date, datetime
from typing import Any

from src.application.ports.consentimiento_cache import ConsentimientoCachePort
from src.domain.clientes.entities import Cliente, ClienteId
from src.domain.clientes.repositories import ClienteRepository
from src.domain.consentimiento.entities import (
    ConsentimientoActual,
    EstadoConsentimiento,
)
from src.domain.consentimiento.repositories import ConsentimientoRepository


class ConsentimientoNoEncontradoError(Exception):
    pass


class ConsentimientoNoOtorgadoError(Exception):
    pass


class PerfilClienteNoEncontradoError(Exception):
    pass


class GestionarConsentimientoUseCase:
    def __init__(
        self,
        consentimiento_repository: ConsentimientoRepository,
        cliente_repository: ClienteRepository,
        cache: ConsentimientoCachePort,
        terms_version: str,
    ) -> None:
        self.consentimiento_repository = consentimiento_repository
        self.cliente_repository = cliente_repository
        self.cache = cache
        self.terms_version = terms_version

    async def actualizar_consentimiento(
        self, cliente_id: uuid.UUID, estado: EstadoConsentimiento
    ) -> ConsentimientoActual:
        cache_entry = await self.cache.obtener(cliente_id)
        if estado == EstadoConsentimiento.REVOCADO:
            await self.cache.guardar(
                cliente_id, EstadoConsentimiento.REVOCADO, None
            )

        actual = await self.consentimiento_repository.actualizar_estado(
            cliente_id, estado, self.terms_version, "web"
        )
        if actual is None:
            await self.cache.invalidar(cliente_id)
            raise ConsentimientoNoEncontradoError

        if estado == EstadoConsentimiento.ACEPTADO:
            perfil = (
                cache_entry.perfil
                if cache_entry is not None
                and cache_entry.estado == EstadoConsentimiento.ACEPTADO
                else None
            )
            await self.cache.guardar(cliente_id, estado, perfil)
        return actual

    async def obtener_perfil_cliente(
        self, cliente_id: uuid.UUID
    ) -> dict[str, Any]:
        cache_entry = await self.cache.obtener(cliente_id)
        if cache_entry is not None:
            if cache_entry.estado != EstadoConsentimiento.ACEPTADO:
                raise ConsentimientoNoOtorgadoError
            if cache_entry.perfil is not None:
                return cache_entry.perfil
            return await self._cargar_perfil_cliente(cliente_id)

        actual = await self.consentimiento_repository.obtener_actual(cliente_id)
        if actual is None or actual.estado != EstadoConsentimiento.ACEPTADO:
            await self.cache.guardar(
                cliente_id, EstadoConsentimiento.REVOCADO, None
            )
            raise ConsentimientoNoOtorgadoError
        return await self._cargar_perfil_cliente(cliente_id)

    async def _cargar_perfil_cliente(
        self, cliente_id: uuid.UUID
    ) -> dict[str, Any]:
        cliente = await self.cliente_repository.obtener_por_id(
            ClienteId(value=cliente_id)
        )
        if cliente is None:
            raise PerfilClienteNoEncontradoError

        perfil = self._serializar_perfil(cliente)
        await self.cache.guardar(
            cliente_id, EstadoConsentimiento.ACEPTADO, perfil
        )
        return perfil

    @staticmethod
    def _serializar_perfil(cliente: Cliente) -> dict[str, Any]:
        return {
            "id": str(cliente.id.value),
            "nombres": cliente.nombres,
            "apellidos": cliente.apellidos,
            "tipo_documento": cliente.tipo_documento,
            "numero_identificacion": cliente.numero_identificacion,
            "correo": cliente.correo,
            "fecha_nacimiento": cliente.fecha_nacimiento.isoformat(),
            "pais_residencia": cliente.pais_residencia,
            "telefono": cliente.telefono,
            "estado_kyc": cliente.estado_kyc.value,
            "fecha_creacion": _isoformat_or_none(cliente.fecha_creacion),
            "fecha_actualizacion": _isoformat_or_none(
                cliente.fecha_actualizacion
            ),
        }


def _isoformat_or_none(value: date | datetime | None) -> str | None:
    return value.isoformat() if value is not None else None