import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _paypal(email="cliente@example.com", **extra):
    return {"payer_email": email, "amount": "1500.50", "currency": "COP", "reference": "pago-1", **extra}


@pytest.mark.parametrize(
    ("email", "estado", "codigo"),
    [
        ("cliente@example.com", "COMPLETED", None),
        ("declined@example.com", "DECLINED", "INSTRUMENT_DECLINED"),
        ("NoFunds.test@example.com", "DECLINED", "INSUFFICIENT_FUNDS"),
    ],
)
async def test_paypal_resuelve_el_escenario_por_correo(client, email, estado, codigo):
    response = await client.post("/paypal/payments", json=_paypal(email))

    assert response.status_code == 201
    cuerpo = response.json()
    assert cuerpo["status"] == estado
    assert cuerpo["failure_code"] == codigo
    assert cuerpo["id"].startswith("PAYPAL_")


async def test_paypal_id_es_estable_por_idempotency_key_y_referencia(client):
    primero = await client.post("/paypal/payments", json=_paypal(), headers={"Idempotency-Key": "k1"})
    repetido = await client.post("/paypal/payments", json=_paypal(), headers={"Idempotency-Key": "k1"})
    otra_clave = await client.post("/paypal/payments", json=_paypal(), headers={"Idempotency-Key": "k2"})
    sin_clave = await client.post("/paypal/payments", json=_paypal())
    otra_referencia = await client.post("/paypal/payments", json=_paypal(reference="pago-2"))

    assert primero.json() == repetido.json()
    assert primero.json()["id"] != otra_clave.json()["id"]
    assert sin_clave.json()["id"] != otra_referencia.json()["id"]


@pytest.mark.parametrize(
    "cambio",
    [
        {"payer_email": "sin-arroba"},
        {"amount": "0"},
        {"amount": "-1"},
        {"currency": "COPP"},
        {"reference": ""},
    ],
)
async def test_paypal_valida_la_solicitud(client, cambio):
    response = await client.post("/paypal/payments", json={**_paypal(), **cambio})

    assert response.status_code == 422


def _tarjeta(numero="4242424242424242", **extra):
    return {"number": numero, "exp_month": 12, "exp_year": 2099, "cvv": "123", **extra}


async def test_tokeniza_sin_devolver_numero_ni_cvv(client):
    response = await client.post("/credit-card/tokens", json=_tarjeta())

    assert response.status_code == 201
    assert response.json() == {"token": "tok_VISA_4242", "brand": "VISA", "last4": "4242"}
    assert "4242424242424242" not in response.text and "123" not in response.json()["token"]


@pytest.mark.parametrize(
    ("numero", "marca"), [("5555555555554444", "MASTERCARD"), ("378282246310005", "AMEX"), ("6011111111111117", "CARD")]
)
async def test_tokeniza_la_marca_segun_el_prefijo(client, numero, marca):
    response = await client.post("/credit-card/tokens", json=_tarjeta(numero))

    assert response.json()["brand"] == marca


@pytest.mark.parametrize(
    "cambio",
    [
        {"number": "1234"},
        {"number": "4242-4242-4242-4242"},
        {"exp_month": 13},
        {"exp_year": 1999},
        {"cvv": "12"},
    ],
)
async def test_tokenizacion_valida_los_datos(client, cambio):
    response = await client.post("/credit-card/tokens", json={**_tarjeta(), **cambio})

    assert response.status_code == 422


def _cargo(token="tok_VISA_4242", **extra):
    return {"token": token, "amount": "99000", "currency": "COP", "reference": "pago-1", **extra}


@pytest.mark.parametrize(
    ("numero", "estado", "codigo"),
    [
        ("4242424242424242", "succeeded", None),
        ("4000000000000002", "declined", "card_declined"),
        ("4000000000009995", "declined", "insufficient_funds"),
        ("4000000000000069", "declined", "expired_card"),
    ],
)
async def test_flujo_tokenizar_y_cobrar_segun_los_ultimos_4_digitos(client, numero, estado, codigo):
    token = (await client.post("/credit-card/tokens", json=_tarjeta(numero))).json()["token"]

    response = await client.post("/credit-card/charges", json=_cargo(token))

    assert response.status_code == 201
    cuerpo = response.json()
    assert (cuerpo["status"], cuerpo["failure_code"]) == (estado, codigo)
    assert cuerpo["last4"] == numero[-4:] and cuerpo["brand"] == "VISA"
    assert cuerpo["id"].startswith("ch_")


async def test_cargo_repetido_con_la_misma_clave_devuelve_la_misma_respuesta(client):
    headers = {"Idempotency-Key": "pago-1"}

    primero = await client.post("/credit-card/charges", json=_cargo(), headers=headers)
    repetido = await client.post("/credit-card/charges", json=_cargo(), headers=headers)

    assert primero.json() == repetido.json()


@pytest.mark.parametrize("token", ["", "4242424242424242", "tok_4242", "tok_visa_4242"])
async def test_cargo_rechaza_tokens_invalidos(client, token):
    response = await client.post("/credit-card/charges", json=_cargo(token))

    assert response.status_code == 422


async def test_paypal_y_tarjeta_estan_separadas_por_prefijo(client):
    assert (await client.post("/payments", json=_paypal())).status_code == 404
    assert (await client.post("/paypal/charges", json=_cargo())).status_code == 404
    assert (await client.post("/credit-card/payments", json=_paypal())).status_code == 404
