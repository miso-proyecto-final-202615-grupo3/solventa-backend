from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


def test_crea_sesion_y_entrega_decision_aprobada(monkeypatch):
    monkeypatch.delenv("MOCK_DIDIT_STATUS", raising=False)
    created = client.post("/v3/session/", json={"workflow_id": "wf", "vendor_data": "cliente-1"}, headers={"x-api-key": "k"})

    decision = client.get(f"/v3/session/{created.json()['session_id']}/decision/", headers={"x-api-key": "k"})

    assert created.status_code == 201
    assert created.json()["session_token"]
    assert decision.json()["status"] == "Approved"


def test_vendor_data_terminado_en_cero_se_rechaza():
    created = client.post("/v3/session/", json={"workflow_id": "wf", "vendor_data": "cliente-10"}, headers={"x-api-key": "k"})

    decision = client.get(f"/v3/session/{created.json()['session_id']}/decision/", headers={"x-api-key": "k"})

    assert decision.json()["status"] == "Declined"


def test_exige_api_key():
    assert client.post("/v3/session/", json={"workflow_id": "wf"}).status_code == 401


def test_sesion_inexistente():
    assert client.get("/v3/session/nada/decision/", headers={"x-api-key": "k"}).status_code == 404
