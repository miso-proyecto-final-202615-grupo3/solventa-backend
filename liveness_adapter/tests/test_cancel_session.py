import pytest
from fastapi import HTTPException

from src.main import _sessions, cancel_session


async def test_cancela_sesion_creada_de_forma_idempotente():
    _sessions["sesion-1"] = {"state": "CREATED"}

    response = await cancel_session("sesion-1")
    repeated_response = await cancel_session("sesion-1")

    assert response.status_code == 204
    assert repeated_response.status_code == 204
    assert _sessions["sesion-1"]["state"] == "CANCELLED"


async def test_rechaza_cancelar_sesion_ya_usada():
    _sessions["sesion-usada"] = {"state": "USED"}

    with pytest.raises(HTTPException) as error:
        await cancel_session("sesion-usada")

    assert error.value.status_code == 409


async def test_rechaza_sesion_inexistente():
    with pytest.raises(HTTPException) as error:
        await cancel_session("desconocida")

    assert error.value.status_code == 404
