import uuid

from fastapi import APIRouter, Depends, Header, status

from src.infrastructure.gateways.identity_service_gateway import (
    IdentityGatewayError,
    IdentityServiceGateway,
)
from src.presentation.dependencies import get_cliente_autenticado, get_identity_service_gateway
from src.presentation.errors import ApiError
from src.presentation.jwt_validator import ClienteAutenticado
from src.presentation.schemas import (
    EstadoConsentimientoBiometricoResponse,
    RegistrarConsentimientoBiometricoRequest,
    RegistrarConsentimientoBiometricoResponse,
)

router = APIRouter(prefix="/consentimientos", tags=["Consentimiento biométrico"])

_RESPUESTAS = {
    401: {"description": "Token ausente, inválido o vencido."},
    404: {"description": "CLIENTE_NO_REGISTRADO."},
    409: {"description": "VERSION_TERMINOS_DESACTUALIZADA."},
    422: {"description": "DATOS_INVALIDOS."},
    503: {"description": "SERVICIO_NO_DISPONIBLE."},
}


@router.get("/biometrico", response_model=EstadoConsentimientoBiometricoResponse, responses=_RESPUESTAS)
async def consultar_consentimiento_biometrico(
    correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    cliente: ClienteAutenticado = Depends(get_cliente_autenticado),
    gateway: IdentityServiceGateway = Depends(get_identity_service_gateway),
) -> EstadoConsentimientoBiometricoResponse:
    """Estado del consentimiento biométrico del cliente autenticado (HU3.1.3)."""
    try:
        result = await gateway.consultar_consentimiento_biometrico(
            cliente.correo, correlation_id or str(uuid.uuid4())
        )
    except IdentityGatewayError as exc:
        raise ApiError.desde_identidad(exc.status_code, exc.detail) from exc
    return EstadoConsentimientoBiometricoResponse.model_validate(result)


@router.post(
    "/biometrico",
    response_model=RegistrarConsentimientoBiometricoResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_RESPUESTAS,
)
async def registrar_consentimiento_biometrico(
    payload: RegistrarConsentimientoBiometricoRequest,
    correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    cliente: ClienteAutenticado = Depends(get_cliente_autenticado),
    gateway: IdentityServiceGateway = Depends(get_identity_service_gateway),
) -> RegistrarConsentimientoBiometricoResponse:
    """Registra la aceptación o el rechazo con fecha, hora y versión del texto legal."""
    try:
        result = await gateway.registrar_consentimiento_biometrico(
            cliente.correo,
            {
                "decision": payload.decision,
                "version_terminos": payload.version_terminos,
                "installation_id": str(payload.installation_id),
                "decidido_en": payload.decidido_en.isoformat(),
            },
            correlation_id or str(uuid.uuid4()),
        )
    except IdentityGatewayError as exc:
        raise ApiError.desde_identidad(exc.status_code, exc.detail) from exc
    return RegistrarConsentimientoBiometricoResponse.model_validate(result)
