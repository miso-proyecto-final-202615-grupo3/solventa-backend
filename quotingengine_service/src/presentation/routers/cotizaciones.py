import uuid
from hmac import compare_digest

from fastapi import APIRouter, Depends, Header, HTTPException, status

from src.application.ports.perfil_cliente_gateway import (
    ClienteNoEncontradoError,
    ConsentimientoNoOtorgadoError,
)
from src.application.pricing.registry import EstrategiaNoRegistradaError
from src.application.use_cases.consultar_catalogo_use_case import (
    ProductoNoEncontradoError,
)
from src.application.use_cases.solicitar_cotizacion_use_case import (
    CondicionesNoConfiguradasError,
    CotizacionNoEncontradaError,
    ParametrosInvalidosError,
    ReglaRatingNoDisponibleError,
    SolicitarCotizacionUseCase,
)
from src.application.use_cases.condiciones_cotizacion_use_case import (
    CondicionesCotizacionUseCase,
    CondicionesDesactualizadasError,
    CondicionesNoEncontradasError,
    CotizacionNoVigenteError,
)
from src.domain.condiciones.entities import DecisionCondiciones
from src.core.config import settings
from src.presentation.dependencies import get_condiciones_cotizacion_use_case, get_solicitar_cotizacion_use_case
from src.presentation.schemas.condiciones_schemas import (
    CondicionesResponse,
    DecisionRequest,
    DecisionResponse,
    EventoTrazabilidadCondicionesResponse,
)
from src.presentation.schemas.cotizacion_schemas import (
    CotizacionResponse,
    SolicitudCotizacionRequest,
    cotizacion_response,
)

router = APIRouter(prefix="/cotizaciones", tags=["Cotizaciones"])


@router.post("", response_model=CotizacionResponse, status_code=status.HTTP_201_CREATED)
async def solicitar_cotizacion(
    payload: SolicitudCotizacionRequest,
    use_case: SolicitarCotizacionUseCase = Depends(get_solicitar_cotizacion_use_case),
) -> CotizacionResponse:
    try:
        detalle = await use_case.solicitar(
            payload.cliente_id,
            payload.producto_codigo,
            payload.parametros,
            payload.socio_id,
        )
    except ProductoNoEncontradoError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Ramo de seguro no encontrado."
        ) from exc
    except ClienteNoEncontradoError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Cliente no encontrado."
        ) from exc
    except ConsentimientoNoOtorgadoError as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "El consentimiento Open Finance no está activo.",
        ) from exc
    except ParametrosInvalidosError as exc:
        raise HTTPException(
            422, detail=exc.errores
        ) from exc
    except (ReglaRatingNoDisponibleError, EstrategiaNoRegistradaError, CondicionesNoConfiguradasError) as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "El ramo de seguro no está disponible para cotizar.",
        ) from exc
    return cotizacion_response(detalle)


@router.get("/{cotizacion_id}", response_model=CotizacionResponse)
async def obtener_cotizacion(
    cotizacion_id: uuid.UUID,
    use_case: SolicitarCotizacionUseCase = Depends(get_solicitar_cotizacion_use_case),
) -> CotizacionResponse:
    try:
        return cotizacion_response(await use_case.obtener(cotizacion_id))
    except CotizacionNoEncontradaError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Cotización no encontrada."
        ) from exc


@router.get("/{cotizacion_id}/condiciones", response_model=CondicionesResponse)
async def obtener_condiciones(
    cotizacion_id: uuid.UUID,
    use_case: CondicionesCotizacionUseCase = Depends(get_condiciones_cotizacion_use_case),
) -> CondicionesResponse:
    try:
        condiciones = await use_case.obtener(cotizacion_id)
        evento = await use_case.ultima_decision(condiciones.condiciones_cotizacion_id)
    except (CotizacionNoEncontradaError, CondicionesNoEncontradasError) as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Condiciones no encontradas.") from exc
    response = CondicionesResponse.model_validate(condiciones, from_attributes=True)
    if evento is not None:
        response.ultima_decision = _decision_response(condiciones.version_condiciones_generales, evento)
    return response


@router.post("/{cotizacion_id}/condiciones/decisiones", response_model=DecisionResponse, status_code=status.HTTP_201_CREATED)
async def decidir_condiciones(
    cotizacion_id: uuid.UUID,
    payload: DecisionRequest,
    use_case: CondicionesCotizacionUseCase = Depends(get_condiciones_cotizacion_use_case),
) -> DecisionResponse:
    try:
        condiciones, evento = await use_case.decidir(
            cotizacion_id, payload.condiciones_cotizacion_id, payload.decision
        )
    except (CotizacionNoEncontradaError, CondicionesNoEncontradasError) as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Condiciones no encontradas.") from exc
    except (CondicionesDesactualizadasError, CotizacionNoVigenteError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Condiciones desactualizadas o cotización no vigente.") from exc
    return _decision_response(condiciones.version_condiciones_generales, evento)


@router.get(
    "/{cotizacion_id}/trazabilidad-condiciones",
    response_model=list[EventoTrazabilidadCondicionesResponse],
    include_in_schema=False,
)
async def consultar_trazabilidad_condiciones(
    cotizacion_id: uuid.UUID,
    internal_token: str | None = Header(default=None, alias="X-Audit-Internal-Token"),
    use_case: CondicionesCotizacionUseCase = Depends(get_condiciones_cotizacion_use_case),
) -> list[EventoTrazabilidadCondicionesResponse]:
    esperado = settings.TRAZABILIDAD_INTERNAL_TOKEN
    if not esperado or not internal_token or not compare_digest(esperado, internal_token):
        raise HTTPException(status_code=403, detail="Consulta interna no autorizada.")
    decisiones = await use_case.decisiones_por_cotizacion(cotizacion_id)
    return [
        EventoTrazabilidadCondicionesResponse(
            evento_id=decision.decision_condiciones_id,
            cotizacion_id=cotizacion_id,
            cliente_id=decision.cliente_id,
            tipo=(
                "CONDICIONES_ACEPTADAS"
                if decision.decision.value == "ACEPTADA"
                else "CONDICIONES_RECHAZADAS"
            ),
            ocurrido_en=decision.decidida_en,
            origen="quotingengine_service",
            actor_id=None,
            resultado=decision.decision.value,
            referencia_id=str(decision.decision_condiciones_id),
            detalles={
                "condiciones_cotizacion_id": str(decision.condiciones_cotizacion_id)
            },
        )
        for decision in decisiones
    ]


def _decision_response(version: str, evento: DecisionCondiciones) -> DecisionResponse:
    return DecisionResponse(
        decision_condiciones_id=evento.decision_condiciones_id,
        condiciones_cotizacion_id=evento.condiciones_cotizacion_id,
        cliente_id=evento.cliente_id,
        version_condiciones_generales=version,
        decision=evento.decision,
        decidida_en=evento.decidida_en,
    )
