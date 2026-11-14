from hmac import compare_digest

from fastapi import APIRouter, Depends, Header, HTTPException

from src.core.config import settings
from src.domain.eventos.repositories import AuditoriaPolizaRepository
from src.domain.polizas.repositories import PolizaRepository
from src.presentation.dependencies import (
    get_auditoria_poliza_repository,
    get_poliza_repository,
)
from src.presentation.schemas.emision_schemas import (
    EventoTrazabilidadPolizaResponse,
    ReferenciaTrazabilidadPolizaResponse,
)

router = APIRouter(prefix="/auditoria-emision", tags=["Auditoría de emisión"])


@router.get(
    "/polizas/numero/{numero}",
    response_model=ReferenciaTrazabilidadPolizaResponse,
    include_in_schema=False,
)
async def consultar_trazabilidad_emision(
    numero: str,
    internal_token: str | None = Header(default=None, alias="X-Audit-Internal-Token"),
    polizas: PolizaRepository = Depends(get_poliza_repository),
    auditoria: AuditoriaPolizaRepository = Depends(get_auditoria_poliza_repository),
) -> ReferenciaTrazabilidadPolizaResponse:
    esperado = settings.TRAZABILIDAD_INTERNAL_TOKEN
    if not esperado or not internal_token or not compare_digest(esperado, internal_token):
        raise HTTPException(status_code=403, detail="Consulta interna no autorizada.")
    poliza = await polizas.obtener_por_numero(numero)
    if poliza is None:
        raise HTTPException(status_code=404, detail="Póliza no encontrada.")
    eventos = await auditoria.listar_por_cotizacion(poliza.cotizacion_id)
    return ReferenciaTrazabilidadPolizaResponse(
        poliza_id=poliza.poliza_id,
        numero=poliza.numero,
        cotizacion_id=poliza.cotizacion_id,
        cliente_id=poliza.cliente_id,
        eventos=[EventoTrazabilidadPolizaResponse.model_validate(evento) for evento in eventos],
    )
