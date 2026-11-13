import uuid
from datetime import datetime
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.pagos.entities import METODO_PAGO_DEFECTO, EstadoPago, MetodoPago


class PagoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    cotizacion_id: uuid.UUID
    cliente_id: uuid.UUID
    metodo_pago: MetodoPago = METODO_PAGO_DEFECTO
    paypal_email: str | None = Field(
        default=None, max_length=254, pattern=r"^[^@\s]+@[^@\s]+$"
    )
    numero_tarjeta: str | None = Field(default=None, pattern=r"^[0-9]{13,19}$", repr=False)
    mes_expiracion: int | None = Field(default=None, strict=True, ge=1, le=12, repr=False)
    anio_expiracion: int | None = Field(default=None, strict=True, ge=2000, le=2100, repr=False)
    cvv: str | None = Field(default=None, pattern=r"^[0-9]{3,4}$", repr=False)

    @model_validator(mode="after")
    def _validar_datos_del_metodo(self) -> Self:
        datos_tarjeta = (self.numero_tarjeta, self.mes_expiracion, self.anio_expiracion, self.cvv)
        if self.metodo_pago == MetodoPago.PAYPAL:
            if not self.paypal_email or any(dato is not None for dato in datos_tarjeta):
                raise ValueError("PAYPAL requiere paypal_email y no admite datos de tarjeta.")
        elif self.paypal_email is not None or any(dato is None for dato in datos_tarjeta):
            raise ValueError("TARJETA_CREDITO requiere numero_tarjeta, mes_expiracion, anio_expiracion y cvv, y no admite paypal_email.")
        return self


class PagoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pago_id: uuid.UUID
    cotizacion_id: uuid.UUID
    cliente_id: uuid.UUID
    monto: Decimal
    moneda: str
    metodo_pago: MetodoPago
    estado: EstadoPago
    codigo_rechazo: str | None
    tarjeta_ultimos4: str | None
    tarjeta_marca: str | None
    creado_en: datetime
    procesado_en: datetime | None


class MetodoPagoResponse(BaseModel):
    codigo: MetodoPago
    por_defecto: bool


class ResumenPagoResponse(BaseModel):
    cotizacion_id: uuid.UUID
    prima_total: Decimal
    moneda: str
    expira_en: datetime
    metodos_pago: list[MetodoPagoResponse]
