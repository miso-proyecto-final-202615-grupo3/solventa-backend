import json
from datetime import datetime, timedelta, timezone

import pytest

BASE = "/api/v1/liveness-adapter"
JPEG = b"\xff\xd8\xff" + b"0" * 32


def _frames():
    return {
        name: (f"{name}.jpg", JPEG + name.encode(), "image/jpeg")
        for name in ("frame_inicio", "frame_gesto", "frame_fin")
    }


def _capturas(start: datetime):
    return {
        "inicio": start.isoformat(),
        "gesto": (start + timedelta(seconds=1)).isoformat(),
        "fin": (start + timedelta(seconds=2)).isoformat(),
    }


async def _start(client, customer_id="cliente-1"):
    response = await client.post(f"{BASE}/liveness/sessions", json={"customer_id": customer_id}, headers={"X-Correlation-Id": "corr-1"})
    assert response.status_code == 201
    return response.json()


async def _verify(client, session_id, nonce="nonce-1", customer_id="cliente-1", **extra):
    metadata = {
        "session_id": session_id,
        "customer_id": customer_id,
        "nonce": nonce,
        "capturas": _capturas(datetime.now(timezone.utc) + timedelta(milliseconds=100)),
        **extra,
    }
    return await client.post(
        f"{BASE}/liveness/verifications", data={"metadata": json.dumps(metadata)}, files=_frames(),
        headers={"X-Correlation-Id": "corr-2"},
    )


async def test_health_no_depende_de_redis(adapter, client):
    adapter["store"].fail = True

    response = await client.get(f"/health")

    assert response.status_code == 200


async def test_sesion_con_el_proveedor_activo_no_expone_el_nombre(adapter, client):
    body = await _start(client)

    assert body["capture"] == {"tipo": "FRAMES", "reto": {"gesto": "BLINK", "nonce": "nonce-1"}}
    assert "propio" not in json.dumps(body)
    stored = adapter["store"].values[body["session_id"]]
    assert stored["nonce_hash"] != "nonce-1"
    assert "nonce-1" not in json.dumps(stored, default=str)


async def test_verificacion_aprobada_marca_la_sesion_usada(adapter, client):
    body = await _start(client)

    response = await _verify(client, body["session_id"])

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert adapter["store"].values[body["session_id"]]["state"] == "USED"


async def test_una_sesion_no_se_puede_verificar_dos_veces(adapter, client):
    body = await _start(client)
    await _verify(client, body["session_id"])

    response = await _verify(client, body["session_id"])

    assert response.status_code == 409
    assert adapter["propio"].verifications == 1


async def test_carrera_en_la_transicion_responde_409(adapter, client, monkeypatch):
    body = await _start(client)

    async def otra_verificacion_gano(*_):
        return False

    monkeypatch.setattr(adapter["store"], "transition", otra_verificacion_gano)
    response = await _verify(client, body["session_id"])

    assert response.status_code == 409
    assert adapter["propio"].verifications == 0


async def test_fallo_de_redis_en_la_transicion_no_reabre_la_carrera(adapter, client, monkeypatch):
    body = await _start(client)

    async def redis_caido(*_):
        raise ConnectionError()

    monkeypatch.setattr(adapter["store"], "transition", redis_caido)
    response = await _verify(client, body["session_id"])

    assert response.status_code == 503
    assert adapter["propio"].verifications == 0


@pytest.mark.parametrize(
    "cambios, codigo",
    [({"nonce": "otro"}, 409), ({"customer_id": "otro-cliente"}, 404)],
)
async def test_rechaza_nonce_o_cliente_distinto(adapter, client, cambios, codigo):
    body = await _start(client)

    response = await _verify(client, body["session_id"], **cambios)

    assert response.status_code == codigo


async def test_proveedor_caido_cancela_la_sesion_frames(adapter, client):
    adapter["propio"].unavailable = True
    body = await _start(client)

    response = await _verify(client, body["session_id"])

    assert response.status_code == 502
    assert adapter["store"].values[body["session_id"]]["state"] == "CANCELLED"


async def test_frame_que_no_es_jpeg_responde_415(adapter, client):
    body = await _start(client)
    metadata = {"session_id": body["session_id"], "customer_id": "cliente-1", "nonce": "nonce-1",
                "capturas": _capturas(datetime.now(timezone.utc) + timedelta(milliseconds=100))}
    files = _frames()
    files["frame_gesto"] = ("frame_gesto.png", b"\x89PNG", "image/png")

    response = await client.post(f"{BASE}/liveness/verifications", data={"metadata": json.dumps(metadata)}, files=files)

    assert response.status_code == 415


async def test_cambio_dinamico_de_proveedor_por_endpoint(adapter, client):
    headers = {"X-Admin-Token": "secreto"}

    changed = await client.put(f"{BASE}/admin/liveness-provider", json={"provider": "didit"}, headers=headers)
    body = await _start(client)

    assert changed.status_code == 200
    assert (await client.get(f"{BASE}/admin/liveness-provider", headers=headers)).json()["provider"] == "didit"
    assert body["capture"]["tipo"] == "SDK"


async def test_admin_exige_token(adapter, client):
    response = await client.put(f"{BASE}/admin/liveness-provider", json={"provider": "didit"})

    assert response.status_code == 403


async def test_admin_rechaza_proveedor_no_registrado(adapter, client):
    response = await client.put(
        f"{BASE}/admin/liveness-provider", json={"provider": "otro"}, headers={"X-Admin-Token": "secreto"}
    )

    assert response.status_code == 422


async def test_sin_cupo_de_didit_usa_el_proveedor_propio(adapter, client):
    adapter["active"].set_active_provider("didit")
    adapter["budget"].allowed = False

    body = await _start(client)

    assert body["capture"]["tipo"] == "FRAMES"
    assert adapter["didit"].started == 0


async def test_sesion_sdk_se_verifica_sin_frames(adapter, client):
    adapter["active"].set_active_provider("didit")
    body = await _start(client)
    metadata = {"session_id": body["session_id"], "customer_id": "cliente-1", "resultado_sdk": "COMPLETED"}

    response = await client.post(f"{BASE}/liveness/verifications", data={"metadata": json.dumps(metadata)})

    assert response.status_code == 200
    assert response.json()["status"] == "approved"


async def test_sesion_sdk_cancelada_no_consulta_al_proveedor(adapter, client):
    adapter["active"].set_active_provider("didit")
    body = await _start(client)
    metadata = {"session_id": body["session_id"], "customer_id": "cliente-1", "resultado_sdk": "CANCELLED"}

    response = await client.post(f"{BASE}/liveness/verifications", data={"metadata": json.dumps(metadata)})

    assert response.status_code == 409
    assert response.json()["detail"]["codigo"] == "SESION_CANCELADA"


async def test_logs_no_contienen_nonce_ni_frames(adapter, client, caplog):
    caplog.set_level("INFO")
    body = await _start(client)
    await _verify(client, body["session_id"])

    text = caplog.text
    assert "liveness_provider=propio" in text
    assert "corr-2" in text
    assert "nonce-1" not in text
    assert "0000000000" not in text
