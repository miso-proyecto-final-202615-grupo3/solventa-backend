import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.infrastructure.gateways.identity_service_gateway import (
    IdentityGatewayError,
    IdentityServiceGateway,
)
from src.presentation.dependencies import get_identity_service_gateway
router = APIRouter(prefix="/clientes", tags=["Clientes"])


@router.post(
    "/registro",
    status_code=status.HTTP_201_CREATED,
)
async def registrar_cliente(
    request: Request,
    gateway: IdentityServiceGateway = Depends(get_identity_service_gateway),
) -> dict:
    try:
        return await gateway.registrar_cliente(
            await request.body(),
            request.headers.get("content-type", "application/json"),
        )
    except IdentityGatewayError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail=exc.detail
        ) from exc


@router.post(
    "/autenticar",
    status_code=status.HTTP_200_OK,
)
async def autenticar_cliente(
    request: Request,
    gateway: IdentityServiceGateway = Depends(get_identity_service_gateway),
) -> dict:
    try:
        return await gateway.autenticar_cliente(
            await request.body(),
            request.headers.get("content-type", "application/json"),
        )
    except IdentityGatewayError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail=exc.detail
        ) from exc


@router.put(
    "/{cliente_id}/consentimiento",
    status_code=status.HTTP_200_OK,
)
async def actualizar_consentimiento(
    cliente_id: uuid.UUID,
    request: Request,
    gateway: IdentityServiceGateway = Depends(get_identity_service_gateway),
) -> dict:
    try:
        return await gateway.actualizar_consentimiento(
            str(cliente_id),
            await request.body(),
            request.headers.get("content-type", "application/json"),
        )
    except IdentityGatewayError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail=exc.detail
        ) from exc


@router.get(
    "/{cliente_id}/perfil",
    status_code=status.HTTP_200_OK,
)
async def obtener_perfil_cliente(
    cliente_id: uuid.UUID,
    gateway: IdentityServiceGateway = Depends(get_identity_service_gateway),
) -> dict:
    try:
        return await gateway.obtener_perfil_cliente(str(cliente_id))
    except IdentityGatewayError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail=exc.detail
        ) from exc


MAX_BODY_KYC_AML_BYTES = 12 * 1024 * 1024


def _headers_verificacion(request: Request) -> dict[str, str]:
    permitidos = ("idempotency-key", "x-correlation-id")
    return {k: v for k, v in request.headers.items() if k in permitidos}


@router.post(
    "/{cliente_id}/verificaciones-kyc-aml",
    status_code=status.HTTP_202_ACCEPTED,
)
async def iniciar_verificacion_kyc_aml(
    cliente_id: uuid.UUID,
    request: Request,
    gateway: IdentityServiceGateway = Depends(get_identity_service_gateway),
) -> dict:
    try:
        declarado = int(request.headers.get("content-length", "0"))
    except ValueError:
        declarado = 0
    if declarado > MAX_BODY_KYC_AML_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail={
                "codigo": "DOCUMENTO_DEMASIADO_GRANDE",
                "mensaje": "Los documentos superan el tamaño permitido.",
            },
        )
    try:
        return await gateway.iniciar_verificacion_kyc_aml(
            str(cliente_id),
            await request.body(),
            request.headers.get("content-type", "multipart/form-data"),
            _headers_verificacion(request),
        )
    except IdentityGatewayError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail=exc.detail
        ) from exc


@router.get(
    "/{cliente_id}/verificaciones-kyc-aml/{verificacion_id}",
    status_code=status.HTTP_200_OK,
)
async def consultar_verificacion_kyc_aml(
    cliente_id: uuid.UUID,
    verificacion_id: uuid.UUID,
    request: Request,
    gateway: IdentityServiceGateway = Depends(get_identity_service_gateway),
) -> dict:
    try:
        return await gateway.consultar_verificacion_kyc_aml(
            str(cliente_id), str(verificacion_id), _headers_verificacion(request)
        )
    except IdentityGatewayError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail=exc.detail
        ) from exc
