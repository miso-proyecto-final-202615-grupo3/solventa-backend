from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status

from src.application.ports.perfilamiento import (
    ClienteCotizacionNoEncontradoError,
    ConsentimientoNoActivoError,
    PerfilamientoNoDisponibleError,
)
from src.application.use_cases.generar_cotizacion_use_case import (
    CotizarCommand,
    GenerarCotizacionUseCase,
)
from src.domain.open_data import CategoriaOpenData
from src.domain.pricing import CategoriaOpenFinance
from src.presentation.dependencies import get_generar_cotizacion_use_case
from src.presentation.schemas.cotizacion_schemas import (
    CotizacionResponse,
    CotizarRequest,
    DesgloseCotizacion,
)

router = APIRouter(prefix="/cotizar", tags=["Cotizaciones"])


@router.post(
    "",
    response_model=CotizacionResponse,
    status_code=status.HTTP_200_OK,
)
async def cotizar(
    payload: CotizarRequest,
    use_case: GenerarCotizacionUseCase = Depends(
        get_generar_cotizacion_use_case
    ),
) -> CotizacionResponse:
    try:
        resultado = await use_case.ejecutar(
            CotizarCommand(
                cliente_id=payload.cliente_id,
                saldo_credito=Decimal(payload.parametros.saldo_credito),
                ubicacion=payload.parametros.ubicacion.model_dump(),
            )
        )
    except ConsentimientoNoActivoError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CONSENTIMIENTO_NO_ACTIVO",
        ) from exc
    except ClienteCotizacionNoEncontradoError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CLIENTE_O_RAMO_NO_ENCONTRADO",
        ) from exc
    except PerfilamientoNoDisponibleError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PERFILAMIENTO_NO_DISPONIBLE",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="PARAMETROS_INVALIDOS",
        ) from exc

    pricing = resultado.pricing
    return CotizacionResponse(
        cotizacion_id=resultado.cotizacion_id,
        estado="COTIZADA",
        ramo=payload.ramo,
        moneda="COP",
        prima_mensual=pricing.prima_total,
        desglose=DesgloseCotizacion(
            prima_base=pricing.prima_base,
            ajustes=pricing.ajuste_open_finance + pricing.ajuste_open_data,
            prima_neta=pricing.prima_neta,
            impuestos=pricing.impuestos,
        ),
        explicacion_ajustes=_explicar_ajustes(
            pricing.categoria_open_finance,
            pricing.factor_open_finance,
            resultado.open_finance_personalizado,
            resultado.categoria_open_data,
        ),
        fuente_perfil=resultado.fuente_perfil,
        vigencia_hasta=resultado.vigencia_hasta,
    )


def _explicar_ajustes(
    categoria_open_finance: CategoriaOpenFinance,
    factor_open_finance: Decimal,
    open_finance_personalizado: bool,
    categoria_open_data: CategoriaOpenData,
) -> list[str]:
    explicaciones = []
    if factor_open_finance < 1:
        explicaciones.append(
            "Descuento Open Finance por perfil financiero excelente."
        )
    elif factor_open_finance > 1:
        explicaciones.append("Recargo Open Finance por perfil de riesgo alto.")
    elif not open_finance_personalizado:
        explicaciones.append(
            "Sin personalización Open Finance; se aplicó el factor estándar."
        )
    elif categoria_open_finance == CategoriaOpenFinance.B:
        explicaciones.append("Sin ajuste Open Finance para perfil estándar.")
    else:
        explicaciones.append("Sin ajuste Open Finance para perfil estándar.")

    if categoria_open_data == CategoriaOpenData.BAJO_RIESGO:
        explicaciones.append("Descuento Open Data por zona de bajo riesgo.")
    elif categoria_open_data == CategoriaOpenData.RIESGO_ELEVADO:
        explicaciones.append("Recargo Open Data por zona de riesgo elevado.")
    else:
        explicaciones.append("Sin ajuste territorial para zona estándar.")
    return explicaciones
