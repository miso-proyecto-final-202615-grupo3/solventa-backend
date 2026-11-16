import hashlib
import logging
from decimal import Decimal

from fastapi import APIRouter, FastAPI, Header
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

app = FastAPI(title="Solventa Mock Payment Provider", version="0.1.0")


@app.middleware("http")
async def log_internal_errors(request, call_next):
    try:
        return await call_next(request)
    except Exception:
        logger.exception(
            "Error interno al procesar %s %s",
            request.method,
            request.url.path,
        )
        raise


def _id(prefijo: str, clave: str) -> str:
    # Sin estado: el mismo Idempotency-Key (o referencia) siempre produce el mismo id.
    return f"{prefijo}_{hashlib.sha256(clave.encode()).hexdigest()[:16]}"


# --- PayPal: pago síncrono; el escenario lo define el correo del pagador -----------------------

paypal = APIRouter(prefix="/paypal", tags=["PayPal"])

_PAYPAL_RECHAZOS = {
    "declined": "INSTRUMENT_DECLINED",
    "nofunds": "INSUFFICIENT_FUNDS",
}


class PayPalPaymentRequest(BaseModel):
    payer_email: str = Field(pattern=r"^[^@\s]+@[^@\s]+$")
    amount: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    reference: str = Field(min_length=1, max_length=100)


@paypal.post("/payments", status_code=201)
def crear_pago_paypal(
    payload: PayPalPaymentRequest,
    idempotency_key: str | None = Header(default=None),
) -> dict:
    usuario = payload.payer_email.split("@")[0].lower()
    codigo = next(
        (c for prefijo, c in _PAYPAL_RECHAZOS.items() if usuario.startswith(prefijo)), None
    )
    return {
        "id": _id("PAYPAL", idempotency_key or payload.reference),
        "status": "DECLINED" if codigo else "COMPLETED",
        "failure_code": codigo,
    }


# --- Tarjeta de crédito: tokenización y cargo síncrono -----------------------------------------

credit_card = APIRouter(prefix="/credit-card", tags=["Tarjeta de crédito"])

# Los últimos 4 dígitos del número definen el escenario.
_TARJETA_RECHAZOS = {
    "0002": "card_declined",
    "9995": "insufficient_funds",
    "0069": "expired_card",
}
_MARCAS = {"3": "AMEX", "4": "VISA", "5": "MASTERCARD"}


class CardTokenRequest(BaseModel):
    number: str = Field(pattern=r"^\d{13,19}$")
    exp_month: int = Field(ge=1, le=12)
    exp_year: int = Field(ge=2000, le=2100)
    cvv: str = Field(pattern=r"^\d{3,4}$")


class CardChargeRequest(BaseModel):
    token: str = Field(pattern=r"^tok_[A-Z]+_\d{4}$")
    amount: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    reference: str = Field(min_length=1, max_length=100)


@credit_card.post("/tokens", status_code=201)
def tokenizar_tarjeta(payload: CardTokenRequest) -> dict:
    marca = _MARCAS.get(payload.number[0], "CARD")
    ultimos4 = payload.number[-4:]
    # El token solo lleva marca y últimos 4: el mock no conserva el número ni el CVV.
    return {"token": f"tok_{marca}_{ultimos4}", "brand": marca, "last4": ultimos4}


@credit_card.post("/charges", status_code=201)
def cobrar_tarjeta(
    payload: CardChargeRequest,
    idempotency_key: str | None = Header(default=None),
) -> dict:
    _, marca, ultimos4 = payload.token.split("_")
    codigo = _TARJETA_RECHAZOS.get(ultimos4)
    return {
        "id": _id("ch", idempotency_key or payload.reference),
        "status": "declined" if codigo else "succeeded",
        "failure_code": codigo,
        "brand": marca,
        "last4": ultimos4,
    }


app.include_router(paypal)
app.include_router(credit_card)
