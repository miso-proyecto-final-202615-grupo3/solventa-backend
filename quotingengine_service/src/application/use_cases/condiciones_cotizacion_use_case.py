import uuid
from datetime import datetime, timezone

from src.application.ports.unit_of_work import UnitOfWork
from src.application.use_cases.solicitar_cotizacion_use_case import CotizacionNoEncontradaError
from src.domain.condiciones.condiciones_cotizacion_repository import CondicionesCotizacionRepository
from src.domain.condiciones.decision_condiciones_repository import DecisionCondicionesRepository
from src.domain.condiciones.entities import CondicionesCotizacion, Decision, DecisionCondiciones
from src.domain.cotizaciones.entities import EstadoCotizacion
from src.domain.cotizaciones.cotizacion_repository import CotizacionRepository


class CondicionesNoEncontradasError(Exception):
    pass


class CondicionesDesactualizadasError(Exception):
    pass


class CotizacionNoVigenteError(Exception):
    pass


class CondicionesCotizacionUseCase:
    def __init__(
        self,
        cotizaciones: CotizacionRepository,
        condiciones: CondicionesCotizacionRepository,
        decisiones: DecisionCondicionesRepository,
        unit_of_work: UnitOfWork,
    ) -> None:
        self.cotizaciones = cotizaciones
        self.condiciones = condiciones
        self.decisiones = decisiones
        self.unit_of_work = unit_of_work

    async def obtener(self, cotizacion_id: uuid.UUID) -> CondicionesCotizacion:
        cotizacion = await self.cotizaciones.obtener_por_id(cotizacion_id)
        if cotizacion is None:
            raise CotizacionNoEncontradaError(str(cotizacion_id))
        return await self._obtener_condiciones(cotizacion_id)

    async def _obtener_condiciones(self, cotizacion_id: uuid.UUID) -> CondicionesCotizacion:
        condiciones = await self.condiciones.obtener_por_cotizacion(cotizacion_id)
        if condiciones is None:
            raise CondicionesNoEncontradasError(str(cotizacion_id))
        return condiciones

    async def decidir(
        self,
        cotizacion_id: uuid.UUID,
        condiciones_id: uuid.UUID,
        decision: Decision,
    ) -> tuple[CondicionesCotizacion, DecisionCondiciones]:
        cotizacion = await self.cotizaciones.obtener_por_id(cotizacion_id)
        if cotizacion is None:
            raise CotizacionNoEncontradaError(str(cotizacion_id))
        condiciones = await self._obtener_condiciones(cotizacion_id)
        if condiciones.condiciones_cotizacion_id != condiciones_id:
            raise CondicionesDesactualizadasError(str(condiciones_id))
        expira_en = cotizacion.expira_en
        if expira_en.tzinfo is None:
            expira_en = expira_en.replace(tzinfo=timezone.utc)
        if cotizacion.estado != EstadoCotizacion.VIGENTE or expira_en <= datetime.now(timezone.utc):
            raise CotizacionNoVigenteError(str(cotizacion_id))
        evento = DecisionCondiciones(
            condiciones_cotizacion_id=condiciones_id,
            cliente_id=cotizacion.cliente_id,
            decision=decision,
        )
        try:
            await self.decisiones.guardar(evento)
            await self.unit_of_work.commit()
        except Exception:
            await self.unit_of_work.rollback()
            raise
        return condiciones, evento

    async def ultima_decision(self, condiciones_id: uuid.UUID) -> DecisionCondiciones | None:
        return await self.decisiones.obtener_ultima(condiciones_id)
