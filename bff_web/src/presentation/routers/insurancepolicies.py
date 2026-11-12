from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from src.core.config import settings
from src.infrastructure.gateways.insurancepolicies_service_gateway import (
    InsurancePoliciesGatewayError,
    InsurancePoliciesServiceGateway,
)
from src.presentation.dependencies import get_insurancepolicies_service_gateway

router = APIRouter(tags=["Pólizas"])
_HEADERS_PERMITIDOS = ("authorization", "idempotency-key", "x-correlation-id")


def _headers(request: Request) -> dict[str, str]:
    return {key: value for key, value in request.headers.items() if key in _HEADERS_PERMITIDOS}


async def _leer_cuerpo(request: Request) -> bytes:
    cuerpo = bytearray()
    async for fragmento in request.stream():
        if len(cuerpo) + len(fragmento) > settings.FIRMA_MAX_REQUEST_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail={
                    "codigo": "FIRMA_DEMASIADO_GRANDE",
                    "mensaje": "La solicitud de firma supera el tamaño permitido.",
                },
            )
        cuerpo.extend(fragmento)
    return bytes(cuerpo)


@router.post(
    "/cotizaciones/{cotizacion_id}/firma-digital",
    status_code=status.HTTP_201_CREATED,
    responses={200: {"description": "Reintento idempotente"}},
    openapi_extra={
        "parameters": [
            {
                "name": "Idempotency-Key",
                "in": "header",
                "required": True,
                "schema": {"type": "string"},
            },
            {
                "name": "X-Correlation-Id",
                "in": "header",
                "required": False,
                "schema": {"type": "string"},
            },
        ],
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["cliente_id", "producto_id", "firma"],
                        "properties": {
                            "cliente_id": {"type": "string", "format": "uuid"},
                            "producto_id": {"type": "string", "format": "uuid"},
                            "firma": {"type": "string", "format": "binary"},
                        },
                    }
                }
            },
        },
    },
)
async def capturar_firma(
    cotizacion_id: UUID,
    request: Request,
    response: Response,
    gateway: InsurancePoliciesServiceGateway = Depends(get_insurancepolicies_service_gateway),
) -> dict[str, Any]:
    payload = await _leer_cuerpo(request)
    headers = _headers(request)
    if "content-type" in request.headers:
        headers["content-type"] = request.headers["content-type"]
    try:
        status_code, body = await gateway.capturar_firma(cotizacion_id, payload, headers)
    except InsurancePoliciesGatewayError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    response.status_code = status_code
    return body


@router.get("/cotizaciones/{cotizacion_id}/firma-digital")
async def consultar_firma(
    cotizacion_id: UUID,
    request: Request,
    response: Response,
    gateway: InsurancePoliciesServiceGateway = Depends(get_insurancepolicies_service_gateway),
) -> dict[str, Any]:
    try:
        status_code, body = await gateway.consultar_firma(cotizacion_id, _headers(request))
    except InsurancePoliciesGatewayError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    response.status_code = status_code
    return body
