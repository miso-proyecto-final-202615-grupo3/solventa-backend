"""HU4.2.3 · API interna de siniestros paramétricos (no se expone en el BFF).

- `POST /eventos-parametricos`: adaptador de la fuente externa (clima, vuelos). `X-Fuente-Token`.
- `GET /eventos-parametricos/{event_id}`: traza del evento para auditoría. `X-Fuente-Token` u operador.
- `PUT /polizas-parametricas/{poliza_id}`: zona o vuelo asegurado de una póliza (supuesto P3). Operador.
"""
import hmac
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, field_serializer

from src.application.use_cases.eventos_parametricos_use_cases import (
    ConsultarEventoParametricoUseCase,
    RecibirEventoParametricoUseCase,
    SuscribirPolizaParametricaUseCase,
)
from src.core.config import settings
from src.domain.siniestros.entities import EventoExterno
from src.domain.siniestros.parametricos import UMBRAL_POR_DEFECTO, CoberturaParametrica
from src.presentation.dependencies import (
    get_consultar_evento_parametrico_use_case,
    get_recibir_evento_parametrico_use_case,
    get_suscribir_poliza_parametrica_use_case,
)
from src.presentation.routers.operador import verificar_operador

router = APIRouter(tags=["Siniestros paramétricos"])

_NO_AUTORIZADO = HTTPException(status_code=403, detail={"codigo": "NO_AUTORIZADO", "mensaje": "No autorizado."})
Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


def _coincide(recibido: str | None, esperado: str) -> bool:
    return bool(esperado and recibido and hmac.compare_digest(recibido, esperado))


def verificar_fuente(x_fuente_token: str | None = Header(default=None, alias="X-Fuente-Token")) -> None:
    if not _coincide(x_fuente_token, settings.EVENTOS_FUENTE_TOKEN):
        raise _NO_AUTORIZADO


def verificar_fuente_u_operador(
    x_fuente_token: str | None = Header(default=None, alias="X-Fuente-Token"),
    x_operador_token: str | None = Header(default=None, alias="X-Operador-Token"),
) -> None:
    if not (_coincide(x_fuente_token, settings.EVENTOS_FUENTE_TOKEN) or _coincide(x_operador_token, settings.OPERADOR_TOKEN)):
        raise _NO_AUTORIZADO


def _iso(valor: datetime | None) -> str | None:
    if valor is None:
        return None
    return valor.isoformat().replace("+00:00", "Z") if valor.tzinfo else valor.isoformat() + "Z"


class EventoParametricoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    fuente: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    tipo: Literal["LLUVIA", "RETRASO_VUELO"]
    ocurrido_en: AwareDatetime
    datos: dict = Field(max_length=20)


class EventoRecibidoResponse(BaseModel):
    event_id: str
    estado: str
    recibido_en: datetime

    @field_serializer("recibido_en")
    def _serializar(self, valor: datetime) -> str:
        return _iso(valor)


class EventoTrazaResponse(EventoRecibidoResponse):
    fuente: str
    tipo: str
    ocurrido_en: datetime
    datos: dict | None
    intentos: int
    ultimo_error: str | None
    procesado_en: datetime | None
    resultado: list[dict] | None

    @field_serializer("ocurrido_en", "procesado_en")
    def _serializar_fechas(self, valor: datetime | None) -> str | None:
        return _iso(valor)

    @classmethod
    def desde(cls, evento: EventoExterno) -> "EventoTrazaResponse":
        return cls(
            event_id=evento.event_id, estado=evento.estado, recibido_en=evento.recibido_en, fuente=evento.fuente,
            tipo=evento.tipo, ocurrido_en=evento.ocurrido_en, datos=evento.datos, intentos=evento.intentos,
            ultimo_error=evento.ultimo_error, procesado_en=evento.procesado_en, resultado=evento.resultado,
        )


class SuscripcionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cliente_id: uuid.UUID
    cobertura: CoberturaParametrica
    indice: Texto
    umbral: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    monto_compensacion: Decimal = Field(gt=0, max_digits=16, decimal_places=2)
    moneda: Literal["COP"] = "COP"


class SuscripcionResponse(BaseModel):
    poliza_id: uuid.UUID
    poliza_numero: str
    cobertura: str
    indice: str
    umbral: Decimal
    monto_compensacion: Decimal
    moneda: str


@router.post(
    "/eventos-parametricos", response_model=EventoRecibidoResponse, status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(verificar_fuente)],
)
async def recibir_evento(
    payload: EventoParametricoRequest,
    response: Response,
    use_case: RecibirEventoParametricoUseCase = Depends(get_recibir_evento_parametrico_use_case),
) -> EventoRecibidoResponse:
    """`202` evento nuevo guardado; `200` repetido (sin efectos); `409 EVENTO_EN_CONFLICTO`; `422` contrato."""
    recibido = await use_case.ejecutar(payload.event_id, payload.fuente, payload.tipo, payload.ocurrido_en, payload.datos)
    if not recibido.nuevo:
        response.status_code = status.HTTP_200_OK
    evento = recibido.evento
    return EventoRecibidoResponse(event_id=evento.event_id, estado=evento.estado, recibido_en=evento.recibido_en)


@router.get(
    "/eventos-parametricos/{event_id}", response_model=EventoTrazaResponse,
    dependencies=[Depends(verificar_fuente_u_operador)],
)
async def consultar_evento(
    event_id: str,
    use_case: ConsultarEventoParametricoUseCase = Depends(get_consultar_evento_parametrico_use_case),
) -> EventoTrazaResponse:
    return EventoTrazaResponse.desde(await use_case.ejecutar(event_id))


@router.put(
    "/polizas-parametricas/{poliza_id}", response_model=SuscripcionResponse, dependencies=[Depends(verificar_operador)]
)
async def suscribir_poliza(
    poliza_id: uuid.UUID,
    payload: SuscripcionRequest,
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    use_case: SuscribirPolizaParametricaUseCase = Depends(get_suscribir_poliza_parametrica_use_case),
) -> SuscripcionResponse:
    """`200` con la suscripción; `404 POLIZA_NO_ENCONTRADA`; `422 POLIZA_NO_PARAMETRICA`; `503` sin MS Pólizas."""
    umbral = payload.umbral if payload.umbral is not None else UMBRAL_POR_DEFECTO[payload.cobertura]
    suscripcion = await use_case.ejecutar(
        poliza_id, payload.cliente_id, payload.cobertura.value, payload.indice, umbral,
        payload.monto_compensacion, payload.moneda, x_correlation_id or str(uuid.uuid4()),
    )
    return SuscripcionResponse(
        poliza_id=suscripcion.poliza_id, poliza_numero=suscripcion.poliza_numero, cobertura=suscripcion.cobertura,
        indice=suscripcion.indice, umbral=suscripcion.umbral, monto_compensacion=suscripcion.monto_compensacion,
        moneda=suscripcion.moneda,
    )
