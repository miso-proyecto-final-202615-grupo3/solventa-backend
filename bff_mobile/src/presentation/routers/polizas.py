"""Billetera de pólizas para la app (HU3.2.1 y HU3.2.2).

El cliente sale del token (`get_cliente_id`); la app nunca envía su identificador. Los nombres de producto y
cobertura se resuelven con el catálogo del Motor de Cotización; si no está disponible, la lista igual se entrega
con `nombre: null` para que la sincronización no falle por un dato accesorio.
"""
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, Response

from src.infrastructure.gateways.insurancepolicies_service_gateway import (
    InsurancePoliciesServiceGateway,
    PoliciesGatewayError,
)
from src.infrastructure.gateways.quotingengine_service_gateway import (
    QuotingEngineGatewayError,
    QuotingEngineServiceGateway,
)
from src.presentation.dependencies import (
    get_cliente_id,
    get_insurancepolicies_service_gateway,
    get_quotingengine_service_gateway,
)
from src.presentation.errors import ApiError
from src.presentation.schemas_polizas import BilleteraPolizasResponse

router = APIRouter(prefix="/polizas", tags=["Pólizas"])
logger = logging.getLogger("uvicorn.error")

_RESPUESTAS = {
    401: {"description": "Token ausente, inválido o vencido."},
    403: {"description": "NO_AUTORIZADO: la póliza es de otro cliente."},
    404: {"description": "CLIENTE_NO_REGISTRADO o certificado no disponible."},
    503: {"description": "SERVICIO_NO_DISPONIBLE."},
}
_DISPOSICION_SEGURA = re.compile(r'^attachment; filename="[A-Za-z0-9._-]{1,120}"$')
_DISPOSICION_POR_DEFECTO = 'attachment; filename="certificado-poliza.pdf"'


def _correlation(correlation_id: str | None) -> str:
    return correlation_id or str(uuid.uuid4())


async def _catalogo(quoting: QuotingEngineServiceGateway) -> dict[str, dict[str, Any]]:
    """`producto_id` → producto del catálogo. Vacío si el Motor de Cotización no responde."""
    try:
        productos = await quoting.listar_productos()
    except QuotingEngineGatewayError as exc:
        logger.warning("polizas_catalogo_no_disponible status=%s", exc.status_code)
        return {}
    return {str(p.get("producto_id")): p for p in productos if isinstance(p, dict)}


def _enriquecer(poliza: dict[str, Any], catalogo: dict[str, dict[str, Any]]) -> dict[str, Any]:
    producto = catalogo.get(str(poliza.get("producto_id")))
    nombres = {
        str(c.get("cobertura_id")): c.get("nombre")
        for c in (producto or {}).get("coberturas", [])
        if isinstance(c, dict)
    }
    return {
        "poliza_id": poliza.get("poliza_id"),
        "numero": poliza.get("numero"),
        "estado": poliza.get("estado"),
        "ramo": poliza.get("ramo") or (producto or {}).get("ramo") or "SEGURO",
        "producto": {"codigo": producto["codigo"], "nombre": producto["nombre"]} if producto else None,
        "vigencia_desde": poliza.get("vigencia_desde"),
        "vigencia_hasta": poliza.get("vigencia_hasta"),
        "emitida_en": poliza.get("emitida_en"),
        "prima_total": poliza.get("prima_total"),
        "coberturas": [
            {
                "cobertura_id": c.get("cobertura_id"),
                "nombre": nombres.get(str(c.get("cobertura_id"))),
                "limite_asegurado": c.get("limite_asegurado"),
                "deducible": c.get("deducible"),
            }
            for c in poliza.get("coberturas", [])
        ],
    }


@router.get("", response_model=BilleteraPolizasResponse, responses=_RESPUESTAS)
async def listar_polizas(
    correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    cliente_id: str = Depends(get_cliente_id),
    policies: InsurancePoliciesServiceGateway = Depends(get_insurancepolicies_service_gateway),
    quoting: QuotingEngineServiceGateway = Depends(get_quotingengine_service_gateway),
) -> BilleteraPolizasResponse:
    """Pólizas del cliente para guardar en el teléfono; la app reemplaza su copia local con esta respuesta."""
    try:
        polizas = await policies.listar_mis_polizas(cliente_id, _correlation(correlation_id))
    except PoliciesGatewayError as exc:
        raise ApiError.desde_servicio(exc.status_code, exc.detail) from exc
    catalogo = await _catalogo(quoting)
    return BilleteraPolizasResponse.model_validate(
        {
            "polizas": [_enriquecer(p, catalogo) for p in polizas],
            "sincronizado_en": datetime.now(timezone.utc),
        }
    )


@router.get(
    "/{poliza_id}/certificado/descarga",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "Certificado en PDF"}, **_RESPUESTAS},
)
async def descargar_certificado(
    poliza_id: uuid.UUID,
    correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    cliente_id: str = Depends(get_cliente_id),
    policies: InsurancePoliciesServiceGateway = Depends(get_insurancepolicies_service_gateway),
) -> Response:
    """PDF del certificado / credencial digital de la póliza."""
    try:
        contenido, disposicion = await policies.descargar_certificado(
            str(poliza_id), cliente_id, _correlation(correlation_id)
        )
    except PoliciesGatewayError as exc:
        raise ApiError.desde_servicio(exc.status_code, exc.detail) from exc
    # El nombre del archivo viaja en una cabecera: solo se reenvía si tiene la forma esperada.
    if not disposicion or not _DISPOSICION_SEGURA.match(disposicion):
        disposicion = _DISPOSICION_POR_DEFECTO
    return Response(content=contenido, media_type="application/pdf", headers={"Content-Disposition": disposicion})
