"""Siniestros para la app (HU4.1.1). Contrato canónico: docs/planning/HU4.1.1-plan-tecnico.md §3.

El cliente sale del token (`get_cliente_id`); la descripción nunca se registra en logs.
"""
import uuid

from fastapi import APIRouter, Depends, Header, Response, status

from src.infrastructure.gateways.insuranceclaims_service_gateway import (
    ClaimsGatewayError,
    InsuranceClaimsServiceGateway,
)
from src.presentation.dependencies import get_cliente_id, get_insuranceclaims_service_gateway
from src.presentation.errors import ApiError
from src.presentation.schemas import PolizasElegiblesResponse, ReportarSiniestroRequest, SiniestroResponse

router = APIRouter(prefix="/siniestros", tags=["Siniestros"])

_RESPUESTAS = {
    400: {"description": "DATOS_INVALIDOS (Idempotency-Key faltante o inválida)."},
    401: {"description": "Token ausente, inválido o vencido."},
    404: {"description": "CLIENTE_NO_REGISTRADO, POLIZA_NO_ENCONTRADA o SINIESTRO_NO_ENCONTRADO."},
    409: {"description": "POLIZA_NO_VIGENTE, FECHA_FUERA_DE_VIGENCIA o IDEMPOTENCIA_CONFLICTO."},
    422: {"description": "DATOS_INVALIDOS, FECHA_INVALIDA o TIPO_NO_PERMITIDO."},
    503: {"description": "SERVICIO_NO_DISPONIBLE."},
}


def _correlation(correlation_id: str | None) -> str:
    return correlation_id or str(uuid.uuid4())


@router.get("/polizas-elegibles", response_model=PolizasElegiblesResponse, responses=_RESPUESTAS)
async def listar_polizas_elegibles(
    correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    cliente_id: str = Depends(get_cliente_id),
    gateway: InsuranceClaimsServiceGateway = Depends(get_insuranceclaims_service_gateway),
) -> PolizasElegiblesResponse:
    """Pólizas vigentes del cliente con los tipos de siniestro que admite cada una."""
    try:
        body = await gateway.listar_polizas_elegibles(cliente_id, _correlation(correlation_id), accept_language)
    except ClaimsGatewayError as exc:
        raise ApiError.desde_servicio(exc.status_code, exc.detail) from exc
    return PolizasElegiblesResponse.model_validate(body)


@router.post(
    "",
    response_model=SiniestroResponse,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"description": "Reintento con la misma Idempotency-Key."}, **_RESPUESTAS},
)
async def reportar_siniestro(
    payload: ReportarSiniestroRequest,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    cliente_id: str = Depends(get_cliente_id),
    gateway: InsuranceClaimsServiceGateway = Depends(get_insuranceclaims_service_gateway),
) -> SiniestroResponse:
    """Crea el siniestro (`201`) o devuelve el ya creado con la misma clave (`200`)."""
    try:
        clave = str(uuid.UUID(idempotency_key or ""))
    except ValueError as exc:
        raise ApiError(400, "DATOS_INVALIDOS", "Falta el header Idempotency-Key o no es un UUID.") from exc
    try:
        status_code, body = await gateway.reportar_siniestro(
            cliente_id, clave, payload.model_dump(mode="json"), _correlation(correlation_id)
        )
    except ClaimsGatewayError as exc:
        raise ApiError.desde_servicio(exc.status_code, exc.detail) from exc
    response.status_code = status.HTTP_200_OK if status_code == status.HTTP_200_OK else status.HTTP_201_CREATED
    return SiniestroResponse.model_validate(body)


@router.get("/{siniestro_id}", response_model=SiniestroResponse, responses=_RESPUESTAS)
async def consultar_siniestro(
    siniestro_id: uuid.UUID,
    correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    cliente_id: str = Depends(get_cliente_id),
    gateway: InsuranceClaimsServiceGateway = Depends(get_insuranceclaims_service_gateway),
) -> SiniestroResponse:
    try:
        body = await gateway.obtener_siniestro(cliente_id, str(siniestro_id), _correlation(correlation_id))
    except ClaimsGatewayError as exc:
        raise ApiError.desde_servicio(exc.status_code, exc.detail) from exc
    return SiniestroResponse.model_validate(body)
