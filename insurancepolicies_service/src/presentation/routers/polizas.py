from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status

from src.domain.eventos.repositories import AuditoriaPolizaRepository
from src.domain.polizas.entities import Poliza
from src.domain.polizas.repositories import PolizaRepository
from src.presentation.dependencies import get_auditoria_poliza_repository, get_poliza_repository
from src.presentation.schemas.polizas import PolizaCoberturaResponse, PolizaResponse

router = APIRouter(prefix="/polizas", tags=["Pólizas"])


async def _response(
    poliza: Poliza, auditoria: AuditoriaPolizaRepository
) -> PolizaResponse:
    eventos = await auditoria.listar_por_cotizacion(poliza.cotizacion_id)
    return PolizaResponse(
        poliza_id=poliza.poliza_id,
        cliente_id=poliza.cliente_id,
        cotizacion_id=poliza.cotizacion_id,
        producto_id=poliza.producto_id,
        numero=poliza.numero,
        estado=poliza.estado,
        vigencia_desde=poliza.vigencia_desde,
        vigencia_hasta=poliza.vigencia_hasta,
        emitida_en=poliza.emitida_en,
        ramo=poliza.ramo,
        prima_total=sum((c.prima for c in poliza.coberturas), start=0),
        coberturas=[PolizaCoberturaResponse.model_validate(c) for c in poliza.coberturas],
        historial=eventos,
    )


@router.get("/mis-polizas", response_model=list[PolizaResponse])
async def listar_mis_polizas(
    client_id: UUID = Header(alias="X-Client-Id"),
    repository: PolizaRepository = Depends(get_poliza_repository),
    auditoria: AuditoriaPolizaRepository = Depends(get_auditoria_poliza_repository),
) -> list[PolizaResponse]:
    polizas = await repository.listar_por_cliente(client_id)
    return [await _response(poliza, auditoria) for poliza in polizas]


@router.get("/{poliza_id}", response_model=PolizaResponse)
async def obtener_poliza(
    poliza_id: UUID,
    client_id: UUID = Header(alias="X-Client-Id"),
    repository: PolizaRepository = Depends(get_poliza_repository),
    auditoria: AuditoriaPolizaRepository = Depends(get_auditoria_poliza_repository),
) -> PolizaResponse:
    poliza = await repository.obtener_por_id(poliza_id)
    if poliza is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Póliza no encontrada.")
    if poliza.cliente_id != client_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No puedes consultar esta póliza.")
    return await _response(poliza, auditoria)
