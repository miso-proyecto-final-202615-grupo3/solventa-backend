import pytest
from fastapi import HTTPException

import src.main as main


@pytest.fixture
def sessions(monkeypatch):
    values = {}

    async def get(session_id):
        return values.get(session_id)

    async def save(session_id, session):
        values[session_id] = session

    monkeypatch.setattr(main, "_get_session", get)
    monkeypatch.setattr(main, "_save_session", save)
    return values


async def test_cancela_sesion_creada_de_forma_idempotente(sessions):
    sessions["sesion-1"] = {"state": "CREATED"}

    response = await main.cancel_session("sesion-1")
    repeated_response = await main.cancel_session("sesion-1")

    assert response.status_code == 204
    assert repeated_response.status_code == 204
    assert sessions["sesion-1"]["state"] == "CANCELLED"


async def test_rechaza_cancelar_sesion_ya_usada(sessions):
    sessions["sesion-usada"] = {"state": "USED"}

    with pytest.raises(HTTPException) as error:
        await main.cancel_session("sesion-usada")

    assert error.value.status_code == 409


async def test_rechaza_sesion_inexistente(sessions):
    with pytest.raises(HTTPException) as error:
        await main.cancel_session("desconocida")

    assert error.value.status_code == 404
