import uuid
from collections.abc import Callable
from datetime import timedelta, tzinfo
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from src.application.ports.cotizaciones import CotizacionGateway
from src.application.ports.generador_pdf import GeneradorCertificadoPdf
from src.application.ports.titulares import TitularGateway
from src.application.use_cases.emitir_poliza_use_case import EmitirPolizaUseCase
from src.application.use_cases.generar_certificado_use_case import GenerarCertificadoPolizaUseCase
from src.domain.certificados.repositories import AlmacenamientoCertificadoRepository
from src.domain.eventos.mensajes import PagoAprobado, PolizaEmitida
from src.domain.firmas.repositories import AlmacenamientoFirmaRepository
from src.infrastructure.gateways.identity_http_client import IdentityHttpClient
from src.infrastructure.gateways.quotingengine_http_client import QuotingEngineHttpClient
from src.infrastructure.persistence.evento_outbox_repository_impl import (
    SqlAlchemyEventoOutboxRepository,
)
from src.infrastructure.persistence.firma_digital_repository_impl import (
    SqlAlchemyFirmaDigitalRepository,
)
from src.infrastructure.persistence.generacion_certificado_repository_impl import (
    SqlAlchemyGeneracionCertificadoRepository,
)
from src.infrastructure.persistence.poliza_repository_impl import SqlAlchemyPolizaRepository


class ManejadorPagoAprobado:
    """Emite la póliza cuando payments_service avisa de que la prima inicial fue pagada."""

    def __init__(
        self,
        session_factory: async_sessionmaker,
        cotizaciones_factory: Callable[[], CotizacionGateway] = QuotingEngineHttpClient,
        titulares_factory: Callable[[], TitularGateway] = IdentityHttpClient,
    ) -> None:
        self._session_factory = session_factory
        self._cotizaciones_factory = cotizaciones_factory
        self._titulares_factory = titulares_factory

    async def __call__(self, payload: dict[str, Any]) -> None:
        pago = PagoAprobado.desde_payload(payload)
        correlation_id = pago.correlation_id or pago.evento_id or str(uuid.uuid4())
        cotizaciones, titulares = self._cotizaciones_factory(), self._titulares_factory()
        try:
            async with self._session_factory() as session:
                caso = EmitirPolizaUseCase(
                    SqlAlchemyPolizaRepository(session),
                    SqlAlchemyFirmaDigitalRepository(session),
                    SqlAlchemyEventoOutboxRepository(session),
                    cotizaciones,
                    titulares,
                    session.commit,
                    session.rollback,
                )
                await caso.ejecutar(pago, correlation_id)
        finally:
            for gateway in (cotizaciones, titulares):
                await gateway.aclose()


class ManejadorPolizaEmitida:
    """Genera el certificado PDF cuando se emitió la póliza."""

    def __init__(
        self,
        session_factory: async_sessionmaker,
        almacenamiento_firmas: AlmacenamientoFirmaRepository,
        almacenamiento_certificados: AlmacenamientoCertificadoRepository,
        generador: GeneradorCertificadoPdf,
        zona_horaria: tzinfo,
        en_proceso_ttl: timedelta,
    ) -> None:
        self._session_factory = session_factory
        self._almacenamiento_firmas = almacenamiento_firmas
        self._almacenamiento_certificados = almacenamiento_certificados
        self._generador = generador
        self._zona_horaria = zona_horaria
        self._en_proceso_ttl = en_proceso_ttl

    async def __call__(self, payload: dict[str, Any]) -> None:
        evento = PolizaEmitida.desde_payload(payload)
        correlation_id = evento.correlation_id or evento.evento_id or str(uuid.uuid4())
        async with self._session_factory() as session:
            caso = GenerarCertificadoPolizaUseCase(
                SqlAlchemyPolizaRepository(session),
                SqlAlchemyFirmaDigitalRepository(session),
                SqlAlchemyGeneracionCertificadoRepository(session),
                self._almacenamiento_firmas,
                self._almacenamiento_certificados,
                self._generador,
                session.commit,
                session.rollback,
                self._zona_horaria,
                self._en_proceso_ttl,
            )
            await caso.ejecutar(evento.poliza_id, correlation_id)
