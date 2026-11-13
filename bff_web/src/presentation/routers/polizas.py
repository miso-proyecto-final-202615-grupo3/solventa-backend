import re
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status

from src.infrastructure.gateways.insurancepolicies_service_gateway import (
    InsurancePoliciesGatewayError,
    InsurancePoliciesServiceGateway,
)
from src.presentation.dependencies import get_insurancepolicies_service_gateway

router = APIRouter(prefix="/polizas", tags=["Pólizas"])

_DISPOSICION_SEGURA = re.compile(r'^attachment; filename="[A-Za-z0-9._-]{1,120}"$')
_DISPOSICION_POR_DEFECTO = 'attachment; filename="certificado-poliza.pdf"'


def _headers_cliente(client_id: UUID, correlation_id: str | None) -> dict[str, str]:
    headers = {"X-Client-Id": str(client_id)}
    if correlation_id:
        headers["X-Correlation-Id"] = correlation_id
    return headers


@router.get("/mis-polizas", status_code=status.HTTP_200_OK)
async def listar_mis_polizas(
    client_id: UUID = Header(alias="X-Client-Id"),
    gateway: InsurancePoliciesServiceGateway = Depends(
        get_insurancepolicies_service_gateway
    ),
) -> list[dict]:
    try:
        return await gateway.listar_mis_polizas(str(client_id))
    except InsurancePoliciesGatewayError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc


@router.get("/{poliza_id}", status_code=status.HTTP_200_OK)
async def obtener_poliza(
    poliza_id: UUID,
    client_id: UUID = Header(alias="X-Client-Id"),
    gateway: InsurancePoliciesServiceGateway = Depends(
        get_insurancepolicies_service_gateway
    ),
) -> dict:
    try:
        return await gateway.obtener_poliza(str(poliza_id), str(client_id))
    except InsurancePoliciesGatewayError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc


@router.get("/{poliza_id}/certificado", status_code=status.HTTP_200_OK)
async def consultar_estado_certificado(
    poliza_id: UUID,
    client_id: UUID = Header(alias="X-Client-Id"),
    correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    gateway: InsurancePoliciesServiceGateway = Depends(
        get_insurancepolicies_service_gateway
    ),
) -> dict[str, Any]:
    try:
        return await gateway.consultar_estado_certificado(
            poliza_id, _headers_cliente(client_id, correlation_id)
        )
    except InsurancePoliciesGatewayError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc


@router.get(
    "/{poliza_id}/certificado/descarga",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "Certificado en PDF"}},
)
async def descargar_certificado(
    poliza_id: UUID,
    client_id: UUID = Header(alias="X-Client-Id"),
    correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    gateway: InsurancePoliciesServiceGateway = Depends(
        get_insurancepolicies_service_gateway
    ),
) -> Response:
    try:
        contenido, disposicion = await gateway.descargar_certificado(
            poliza_id, _headers_cliente(client_id, correlation_id)
        )
    except InsurancePoliciesGatewayError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc
    # El nombre del archivo viaja en una cabecera: solo se reenvía si tiene la forma esperada.
    if not disposicion or not _DISPOSICION_SEGURA.match(disposicion):
        disposicion = _DISPOSICION_POR_DEFECTO
    return Response(
        content=contenido,
        media_type="application/pdf",
        headers={
            "Content-Disposition": disposicion,
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
