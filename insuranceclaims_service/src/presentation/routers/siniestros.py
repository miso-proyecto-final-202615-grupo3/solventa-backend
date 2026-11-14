"""API interna de siniestros (solo red interna; la consume el BFF Móvil). HU4.1.1.

El dueño llega en `X-Cliente-Id` (lo resuelve el BFF desde el token); la app nunca lo envía.
"""
import uuid

from fastapi import APIRouter, Depends, Header, Response, status

from src.application.use_cases.consultar_siniestro_use_case import ConsultarSiniestroUseCase
from src.application.use_cases.listar_polizas_elegibles_use_case import ListarPolizasElegiblesUseCase
from src.application.use_cases.reportar_siniestro_use_case import ReporteSiniestroCmd, ReportarSiniestroUseCase
from src.domain.siniestros.catalogo import CatalogoTiposSiniestro, idioma_de
from src.presentation.dependencies import (
    get_catalogo,
    get_consultar_siniestro_use_case,
    get_listar_polizas_elegibles_use_case,
    get_reportar_siniestro_use_case,
)
from src.presentation.schemas.siniestros import (
    PolizaElegibleResponse,
    PolizasElegiblesResponse,
    ProductoResponse,
    ReportarSiniestroRequest,
    SiniestroResponse,
    TipoSiniestroCatalogoResponse,
    TipoSiniestroResponse,
    TiposSiniestroResponse,
)

router = APIRouter(prefix="/siniestros", tags=["Siniestros"])
router_tipos = APIRouter(prefix="/tipos-siniestro", tags=["Catálogo de tipos de siniestro"])


def _correlation(correlation_id: str | None) -> str:
    return correlation_id or str(uuid.uuid4())


@router.get("/polizas-elegibles", response_model=PolizasElegiblesResponse)
async def listar_polizas_elegibles(
    cliente_id: uuid.UUID = Header(alias="X-Cliente-Id"),
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    use_case: ListarPolizasElegiblesUseCase = Depends(get_listar_polizas_elegibles_use_case),
) -> PolizasElegiblesResponse:
    elegibles = await use_case.ejecutar(cliente_id, _correlation(correlation_id), idioma_de(accept_language))
    return PolizasElegiblesResponse(
        polizas=[
            PolizaElegibleResponse(
                poliza_id=e.poliza.poliza_id,
                numero=e.poliza.numero,
                producto=ProductoResponse(codigo=e.poliza.producto_codigo, nombre=e.poliza.producto_nombre),
                vigencia_desde=e.poliza.vigencia_desde,
                vigencia_hasta=e.poliza.vigencia_hasta,
                tipos_siniestro=[TipoSiniestroResponse.desde(t) for t in e.tipos],
            )
            for e in elegibles
        ]
    )


@router.post(
    "",
    response_model=SiniestroResponse,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"description": "Reintento con la misma Idempotency-Key: el siniestro ya creado."}},
)
async def reportar_siniestro(
    payload: ReportarSiniestroRequest,
    response: Response,
    cliente_id: uuid.UUID = Header(alias="X-Cliente-Id"),
    idempotency_key: uuid.UUID = Header(alias="Idempotency-Key"),
    correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    use_case: ReportarSiniestroUseCase = Depends(get_reportar_siniestro_use_case),
) -> SiniestroResponse:
    resultado = await use_case.ejecutar(
        ReporteSiniestroCmd(
            cliente_id=cliente_id,
            clave_idempotencia=str(idempotency_key),
            poliza_id=payload.poliza_id,
            tipo=payload.tipo,
            descripcion=payload.descripcion,
            ocurrido_en=payload.ocurrido_en,
        ),
        _correlation(correlation_id),
    )
    if resultado.repetido:
        response.status_code = status.HTTP_200_OK
    return SiniestroResponse.desde(resultado.siniestro)


@router.get("/{siniestro_id}", response_model=SiniestroResponse)
async def consultar_siniestro(
    siniestro_id: uuid.UUID,
    cliente_id: uuid.UUID = Header(alias="X-Cliente-Id"),
    use_case: ConsultarSiniestroUseCase = Depends(get_consultar_siniestro_use_case),
) -> SiniestroResponse:
    return SiniestroResponse.desde(await use_case.ejecutar(siniestro_id, cliente_id))


@router_tipos.get("", response_model=TiposSiniestroResponse)
async def listar_tipos_siniestro(
    producto_codigo: str | None = None,
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    catalogo: CatalogoTiposSiniestro = Depends(get_catalogo),
) -> TiposSiniestroResponse:
    """Consulta de referencia del catálogo para cualquier consumidor (web, back-office, paramétrico)."""
    tipos = await catalogo.listar(producto_codigo, idioma_de(accept_language))
    return TiposSiniestroResponse(tipos=[TipoSiniestroCatalogoResponse.desde(t) for t in tipos])
