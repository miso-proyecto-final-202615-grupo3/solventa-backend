"""Casos de uso de evidencias y ubicación del siniestro (HU4.1.2).

Cada evidencia es independiente (solicitar → subir directo al almacenamiento → confirmar): una que
falle no afecta al siniestro ni a las demás. Nunca se registran URL firmadas ni coordenadas.
"""
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.almacen_evidencias import AlmacenEvidenciasPort, AlmacenNoDisponible, CargaPrefirmada
from src.domain.siniestros.catalogo import CatalogoTiposSiniestro
from src.domain.siniestros.entities import Siniestro
from src.domain.siniestros.errores import (
    CargaExpirada,
    CargaNoEncontrada,
    EvidenciaNoEncontrada,
    EvidenciaRechazada,
    FechaInvalida,
    IdempotenciaConflicto,
    ServicioNoDisponible,
    SiniestroNoAdmiteEvidencias,
    SiniestroNoEncontrado,
)
from src.domain.siniestros.evidencias import (
    EstadoEvidencia,
    EvidenciaSiniestro,
    OrigenEvidencia,
    TipoEvidencia,
    clave_objeto,
)
from src.domain.siniestros.politica_evidencias import PoliticaEvidencias
from src.domain.siniestros.repositories import EvidenciaRepository, SiniestroRepository
from src.domain.siniestros.ubicacion import UbicacionSiniestro

logger = logging.getLogger(__name__)

TOLERANCIA_RELOJ = timedelta(minutes=5)
BYTES_FIRMA = 12
_VIGENTES = {EstadoEvidencia.PENDIENTE.value, EstadoEvidencia.CARGADA.value}


@dataclass(frozen=True)
class SolicitudCargaCmd:
    siniestro_id: uuid.UUID
    cliente_id: uuid.UUID
    tipo: TipoEvidencia
    content_type: str
    tamano_bytes: int
    origen: OrigenEvidencia
    capturada_en: datetime
    clave_idempotencia: str | None = None


@dataclass(frozen=True)
class SolicitudCargaResultado:
    evidencia: EvidenciaSiniestro
    carga: CargaPrefirmada | None  # None: la evidencia de esa clave ya está CARGADA
    tamano_max_bytes: int
    reutilizada: bool = False


@dataclass(frozen=True)
class SiniestroDetalle:
    siniestro: Siniestro
    evidencias: list[EvidenciaSiniestro]


class SolicitarCargaEvidenciaUseCase:
    def __init__(
        self,
        session: AsyncSession,
        siniestros: SiniestroRepository,
        evidencias: EvidenciaRepository,
        catalogo: CatalogoTiposSiniestro,
        almacen: AlmacenEvidenciasPort,
        politica: PoliticaEvidencias,
        reloj: Callable[[], datetime],
        prefijo: str,
    ) -> None:
        self.session = session
        self.siniestros = siniestros
        self.evidencias = evidencias
        self.catalogo = catalogo
        self.almacen = almacen
        self.politica = politica
        self.reloj = reloj
        self.prefijo = prefijo

    async def ejecutar(self, cmd: SolicitudCargaCmd, correlation_id: str) -> SolicitudCargaResultado:
        ahora = self.reloj()
        if cmd.capturada_en > ahora + TOLERANCIA_RELOJ:
            raise FechaInvalida("La fecha de captura no puede ser futura.")
        # Bloquea la fila del siniestro: dos solicitudes simultáneas no superan el máximo.
        siniestro = await self.siniestros.obtener_de_cliente_para_actualizar(cmd.siniestro_id, cmd.cliente_id)
        if siniestro is None:
            raise SiniestroNoEncontrado()
        self.politica.validar_estado(siniestro)
        tipo_siniestro = await self.catalogo.obtener(siniestro.producto_codigo or "", siniestro.tipo)
        if tipo_siniestro is None:
            raise SiniestroNoAdmiteEvidencias()

        tamano_max = self.politica.max_bytes(cmd.tipo)
        # Reintento de la app con la misma clave (respuesta perdida, app cerrada, sesión vencida): se reutiliza
        # la evidencia en vez de crear otra que ocupe un cupo más.
        previa = None
        if cmd.clave_idempotencia:
            previa = await self.evidencias.obtener_por_clave(siniestro.siniestro_id, cmd.clave_idempotencia)
        if previa is not None and previa.tipo != cmd.tipo.value:
            raise IdempotenciaConflicto()
        if previa is not None and previa.estado == EstadoEvidencia.CARGADA.value:
            return SolicitudCargaResultado(previa, None, tamano_max, reutilizada=True)
        if previa is not None and previa.estado == EstadoEvidencia.RECHAZADA.value:
            raise EvidenciaRechazada()

        vigentes = 0
        for existente in await self.evidencias.listar_de_siniestro(siniestro.siniestro_id):
            if existente.expirar_si_vencida(ahora):
                await self.evidencias.actualizar(existente)  # D12: las vencidas no cuentan
            elif (
                existente.tipo == cmd.tipo.value
                and existente.estado in _VIGENTES
                and (previa is None or existente.evidencia_id != previa.evidencia_id)
            ):
                vigentes += 1
        self.politica.validar_solicitud(
            siniestro, tipo_siniestro.reglas, cmd.tipo, cmd.content_type, cmd.tamano_bytes, vigentes
        )

        expira_en = ahora + self.politica.ttl(cmd.tipo)
        if previa is not None:
            previa.renovar(cmd.tamano_bytes, expira_en)
            evidencia = previa
        else:
            evidencia_id = uuid.uuid4()
            evidencia = EvidenciaSiniestro(
                siniestro_id=siniestro.siniestro_id,
                tipo=cmd.tipo.value,
                content_type=cmd.content_type.lower(),
                tamano_declarado=cmd.tamano_bytes,
                origen=cmd.origen.value,
                capturada_en=cmd.capturada_en,
                objeto_clave=clave_objeto(self.prefijo, siniestro.siniestro_id, evidencia_id, cmd.tipo),
                estado=EstadoEvidencia.PENDIENTE.value,
                solicitada_en=ahora,
                expira_en=expira_en,
                evidencia_id=evidencia_id,
                clave_idempotencia=cmd.clave_idempotencia,
            )
        try:
            if previa is not None:
                await self.evidencias.actualizar(evidencia)
            else:
                await self.evidencias.guardar(evidencia)
            carga = await self.almacen.generar_carga(
                evidencia.objeto_clave, evidencia.content_type, tamano_max, self.politica.ttl(cmd.tipo)
            )
            await self.session.commit()
        except AlmacenNoDisponible as exc:
            await self.session.rollback()
            raise ServicioNoDisponible() from exc
        logger.info(
            "evidencia_solicitada siniestro=%s tipo=%s reutilizada=%s correlation_id=%s",
            siniestro.numero, evidencia.tipo, previa is not None, correlation_id,
        )
        return SolicitudCargaResultado(evidencia, carga, tamano_max, reutilizada=previa is not None)


class ConfirmarCargaEvidenciaUseCase:
    def __init__(
        self,
        session: AsyncSession,
        siniestros: SiniestroRepository,
        evidencias: EvidenciaRepository,
        almacen: AlmacenEvidenciasPort,
        politica: PoliticaEvidencias,
        reloj: Callable[[], datetime],
    ) -> None:
        self.session = session
        self.siniestros = siniestros
        self.evidencias = evidencias
        self.almacen = almacen
        self.politica = politica
        self.reloj = reloj

    async def ejecutar(
        self, siniestro_id: uuid.UUID, evidencia_id: uuid.UUID, cliente_id: uuid.UUID, correlation_id: str
    ) -> EvidenciaSiniestro:
        if await self.siniestros.obtener_de_cliente(siniestro_id, cliente_id) is None:
            raise EvidenciaNoEncontrada()
        evidencia = await self.evidencias.obtener_de_siniestro(evidencia_id, siniestro_id)
        if evidencia is None:
            raise EvidenciaNoEncontrada()
        if evidencia.estado == EstadoEvidencia.CARGADA.value:
            return evidencia  # idempotente
        if evidencia.estado == EstadoEvidencia.RECHAZADA.value:
            raise EvidenciaRechazada()
        if evidencia.estado == EstadoEvidencia.EXPIRADA.value:
            raise CargaExpirada()

        ahora = self.reloj()
        try:
            metadatos = await self.almacen.metadatos(evidencia.objeto_clave)
            if metadatos is None:
                if evidencia.expirar_si_vencida(ahora):
                    await self.evidencias.actualizar(evidencia)
                    await self.session.commit()
                    raise CargaExpirada()
                raise CargaNoEncontrada()
            tipo = TipoEvidencia(evidencia.tipo)
            motivo = None
            if metadatos.tamano != evidencia.tamano_declarado or metadatos.tamano > self.politica.max_bytes(tipo):
                motivo = "TAMANO_DISTINTO"
            elif metadatos.content_type.lower() != evidencia.content_type:
                motivo = "TIPO_DISTINTO"
            elif not metadatos.cifrado:
                motivo = "SIN_CIFRADO"
            elif not self.politica.firma_valida(tipo, await self.almacen.leer_inicio(evidencia.objeto_clave, BYTES_FIRMA)):
                motivo = "CONTENIDO_INVALIDO"
            if motivo:
                await self.almacen.eliminar(evidencia.objeto_clave)
                evidencia.rechazar(motivo)
                await self.evidencias.actualizar(evidencia)
                await self.session.commit()
                logger.info("evidencia_rechazada motivo=%s correlation_id=%s", motivo, correlation_id)
                raise EvidenciaRechazada()
        except AlmacenNoDisponible as exc:
            await self.session.rollback()
            raise ServicioNoDisponible() from exc

        evidencia.confirmar(metadatos.tamano, ahora)
        await self.evidencias.actualizar(evidencia)
        await self.session.commit()
        logger.info("evidencia_cargada tipo=%s correlation_id=%s", evidencia.tipo, correlation_id)
        return evidencia


class RegistrarUbicacionUseCase:
    def __init__(
        self,
        session: AsyncSession,
        siniestros: SiniestroRepository,
        politica: PoliticaEvidencias,
        reloj: Callable[[], datetime],
    ) -> None:
        self.session = session
        self.siniestros = siniestros
        self.politica = politica
        self.reloj = reloj

    async def ejecutar(self, siniestro_id: uuid.UUID, cliente_id: uuid.UUID, ubicacion: UbicacionSiniestro) -> Siniestro:
        ahora = self.reloj()
        if ubicacion.capturada_en > ahora + TOLERANCIA_RELOJ:
            raise FechaInvalida("La fecha de captura no puede ser futura.")
        siniestro = await self.siniestros.obtener_de_cliente_para_actualizar(siniestro_id, cliente_id)
        if siniestro is None:
            raise SiniestroNoEncontrado()
        self.politica.validar_estado(siniestro)
        siniestro.registrar_ubicacion(ubicacion, ahora)
        await self.siniestros.actualizar(siniestro)
        await self.session.commit()
        return siniestro


class ConsultarDetalleSiniestroUseCase:
    """Siniestro del cliente con su ubicación y sus evidencias vigentes (sin las vencidas)."""

    def __init__(self, siniestros: SiniestroRepository, evidencias: EvidenciaRepository, reloj: Callable[[], datetime]) -> None:
        self.siniestros = siniestros
        self.evidencias = evidencias
        self.reloj = reloj

    async def ejecutar(self, siniestro_id: uuid.UUID, cliente_id: uuid.UUID) -> SiniestroDetalle:
        siniestro = await self.siniestros.obtener_de_cliente(siniestro_id, cliente_id)
        if siniestro is None:
            raise SiniestroNoEncontrado()
        ahora = self.reloj()
        evidencias = [
            e for e in await self.evidencias.listar_de_siniestro(siniestro_id)
            if e.estado != EstadoEvidencia.EXPIRADA.value and not e.vencida(ahora)
        ]
        return SiniestroDetalle(siniestro, evidencias)
