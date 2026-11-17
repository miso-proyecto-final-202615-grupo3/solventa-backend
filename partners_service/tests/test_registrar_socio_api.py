async def test_registra_socio_activo_y_audita_actor(socios_client):
    client, repository = socios_client

    response = await client.post(
        "/api/v1/partners-service/socios",
        headers={"X-Partners-Internal-Token": "test-internal-token", "X-Actor-Id": "operator-123"},
        json={
            "nombre": " Banco Andino ",
            "correo": "socio@yopmail.com",
            "tipo_socio": " Banco ",
            "canal_integracion": " API ",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["nombre"] == "Banco Andino"
    assert body["tipo_socio"] == "Banco"
    assert body["canal_integracion"] == "API"
    assert body["correo"] == "socio@yopmail.com"
    assert body["estado"] == "ACTIVO"
    assert body["id"]
    assert body["creado_en"]
    assert len(repository.socios) == 1
    assert len(repository.eventos) == 1
    assert repository.eventos[0].actor_id == "operator-123"
    assert repository.eventos[0].accion == "REGISTRO"


async def test_rechaza_registro_sin_token_interno(socios_client):
    client, repository = socios_client

    response = await client.post(
        "/api/v1/partners-service/socios",
        headers={"X-Actor-Id": "operator-123"},
        json={
            "nombre": "Banco Andino",
            "correo": "socio@yopmail.com",
            "tipo_socio": "Banco",
            "canal_integracion": "API",
        },
    )

    assert response.status_code == 401
    assert repository.socios == []


async def test_rechaza_campos_vacios(socios_client):
    client, repository = socios_client

    response = await client.post(
        "/api/v1/partners-service/socios",
        headers={"X-Partners-Internal-Token": "test-internal-token", "X-Actor-Id": "operator-123"},
        json={"nombre": " ", "correo": "socio@yopmail.com", "tipo_socio": "Banco", "canal_integracion": "API"},
    )

    assert response.status_code == 422
    assert repository.socios == []


async def test_rechaza_correo_duplicado(socios_client):
    client, repository = socios_client
    payload = {
        "nombre": "Banco Andino",
        "correo": "socio@yopmail.com",
        "tipo_socio": "Banco",
        "canal_integracion": "API",
    }
    headers = {"X-Partners-Internal-Token": "test-internal-token", "X-Actor-Id": "operator-123"}

    assert (await client.post("/api/v1/partners-service/socios", headers=headers, json=payload)).status_code == 201
    response = await client.post("/api/v1/partners-service/socios", headers=headers, json=payload)

    assert response.status_code == 409
    assert response.json() == {"detail": "Ya existe un socio con ese correo."}
    assert len(repository.socios) == 1
