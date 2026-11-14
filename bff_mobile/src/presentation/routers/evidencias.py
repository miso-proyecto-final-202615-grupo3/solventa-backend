"""Evidencias y ubicación del siniestro para la app (HU4.1.2). Contrato canónico: docs/planning/HU4.1.2-plan-tecnico.md §3.

El archivo no pasa por aquí: la app lo sube directo al almacenamiento con la carga prefirmada.
Nunca se registran la URL firmada, los campos de la política ni las coordenadas.
"""
import uuid

from fastapi import APIRouter, Depends, Header, Response, status

from src.infrastructure.gateways.insuranceclaims_service_gateway import (
    ClaimsGatewayError,
    InsuranceClaimsServiceGateway,
)
from src.presentation.dependencies import get_cliente_id, get_insuranceclaims_service_gateway
from src.presentation.errors import ApiError
from src.presentation.schemas import (
    EvidenciaResponse,
    RegistrarUbicacionResponse,
    SolicitudCargaRequest,
    SolicitudCargaResponse,
    UbicacionRequest,
)

router = APIRouter(prefix="/siniestros", tags=["Evidencias del siniestro"])

_RESPUESTAS = {
    401: {"description": "Token ausente, inválido o vencido."},
    404: {"description": "SINIESTRO_NO_ENCONTRADO o EVIDENCIA_NO_ENCONTRADA."},
    409: {"description": "SINIESTRO_NO_ADMITE_EVIDENCIAS, LIMITE_EVIDENCIAS, CARGA_NO_ENCONTRADA o CARGA_EXPIRADA."},
    413: {"description": "EVIDENCIA_DEMASIADO_GRANDE."},
    415: {"description": "FORMATO_NO_SOPORTADO."},
    422: {"description": "DATOS_INVALIDOS, TIPO_EVIDENCIA_NO_PERMITIDO o EVIDENCIA_RECHAZADA."},
    503: {"description": "SERVICIO_NO_DISPONIBLE."},
}


def _correlation(correlation_id: str | None) -> str:
    return correlation_id or str(uuid.uuid4())


@router.post(
    "/{siniestro_id}/evidencias",
    response_model=SolicitudCargaResponse,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"description": "Reintento con la misma Idempotency-Key: la misma evidencia (carga nueva, o `carga: null` si ya está CARGADA)."}, **_RESPUESTAS},
)
async def solicitar_carga(
    siniestro_id: uuid.UUID,
    payload: SolicitudCargaRequest,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    cliente_id: str = Depends(get_cliente_id),
    gateway: InsuranceClaimsServiceGateway = Depends(get_insuranceclaims_service_gateway),
) -> SolicitudCargaResponse:
    """Registra la evidencia y devuelve la carga prefirmada (`url` + `campos`) para subir el archivo.

    `Idempotency-Key` es opcional (la app manda una por evidencia local): repetir la solicitud no ocupa otro cupo.
    """
    clave = None
    if idempotency_key is not None:
        try:
            clave = str(uuid.UUID(idempotency_key))
        except ValueError as exc:
            raise ApiError(400, "DATOS_INVALIDOS", "El header Idempotency-Key no es un UUID.") from exc
    try:
        status_code, body = await gateway.solicitar_carga_evidencia(
            cliente_id, str(siniestro_id), payload.model_dump(mode="json"), _correlation(correlation_id), clave
        )
    except ClaimsGatewayError as exc:
        raise ApiError.desde_servicio(exc.status_code, exc.detail) from exc
    response.status_code = status.HTTP_200_OK if status_code == status.HTTP_200_OK else status.HTTP_201_CREATED
    return SolicitudCargaResponse.model_validate(body)


@router.post(
    "/{siniestro_id}/evidencias/{evidencia_id}/confirmacion",
    response_model=EvidenciaResponse,
    responses=_RESPUESTAS,
)
async def confirmar_carga(
    siniestro_id: uuid.UUID,
    evidencia_id: uuid.UUID,
    correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    cliente_id: str = Depends(get_cliente_id),
    gateway: InsuranceClaimsServiceGateway = Depends(get_insuranceclaims_service_gateway),
) -> EvidenciaResponse:
    """Confirma que el archivo se subió; el servicio lo verifica. Idempotente."""
    try:
        body = await gateway.confirmar_carga_evidencia(
            cliente_id, str(siniestro_id), str(evidencia_id), _correlation(correlation_id)
        )
    except ClaimsGatewayError as exc:
        raise ApiError.desde_servicio(exc.status_code, exc.detail) from exc
    return EvidenciaResponse.model_validate(body)


@router.put("/{siniestro_id}/ubicacion", response_model=RegistrarUbicacionResponse, responses=_RESPUESTAS)
async def registrar_ubicacion(
    siniestro_id: uuid.UUID,
    payload: UbicacionRequest,
    correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    cliente_id: str = Depends(get_cliente_id),
    gateway: InsuranceClaimsServiceGateway = Depends(get_insuranceclaims_service_gateway),
) -> RegistrarUbicacionResponse:
    """Registra o reemplaza la ubicación del evento."""
    try:
        body = await gateway.registrar_ubicacion(
            cliente_id, str(siniestro_id), payload.model_dump(mode="json"), _correlation(correlation_id)
        )
    except ClaimsGatewayError as exc:
        raise ApiError.desde_servicio(exc.status_code, exc.detail) from exc
    return RegistrarUbicacionResponse.model_validate(body)
