PREFIX = "/api/v1/liveness-adapter/liveness/sessions"


async def test_cancela_sesion_creada_de_forma_idempotente(adapter, client):
    adapter["store"].values["sesion-1"] = {"state": "CREATED"}

    first = await client.post(f"{PREFIX}/sesion-1/cancel")
    second = await client.post(f"{PREFIX}/sesion-1/cancel")

    assert first.status_code == 204
    assert second.status_code == 204
    assert adapter["store"].values["sesion-1"]["state"] == "CANCELLED"


async def test_rechaza_cancelar_sesion_ya_usada(adapter, client):
    adapter["store"].values["sesion-usada"] = {"state": "USED"}

    response = await client.post(f"{PREFIX}/sesion-usada/cancel")

    assert response.status_code == 409


async def test_rechaza_sesion_inexistente(adapter, client):
    response = await client.post(f"{PREFIX}/desconocida/cancel")

    assert response.status_code == 404


async def test_redis_caido_responde_503(adapter, client):
    adapter["store"].fail = True

    response = await client.post(f"{PREFIX}/sesion-1/cancel")

    assert response.status_code == 503
