import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from src.application.ports.perfil_cliente_gateway import (
    ClienteNoEncontradoError,
    ConsentimientoNoOtorgadoError,
)
from src.application.pricing.registry import EstrategiaNoRegistradaError
from src.application.use_cases.consultar_catalogo_use_case import (
    ProductoNoEncontradoError,
)
from src.application.use_cases.solicitar_cotizacion_use_case import (
    CotizacionNoEncontradaError,
    ParametrosInvalidosError,
    ReglaRatingNoDisponibleError,
    SolicitarCotizacionUseCase,
)
from src.presentation.dependencies import get_solicitar_cotizacion_use_case
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
    except (ReglaRatingNoDisponibleError, EstrategiaNoRegistradaError) as exc:
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
