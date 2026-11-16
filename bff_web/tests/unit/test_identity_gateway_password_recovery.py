import httpx

from src.infrastructure.gateways.identity_service_gateway import (
    IdentityServiceGateway,
)


async def test_reenvia_solicitud_de_recuperacion_a_identity():
    async def handle(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/v1/identity-service/clientes/recuperar-clave"
        assert request.read() == b'{"correo":"ana@example.com"}'
        return httpx.Response(202, json={"mensaje": "Si existe una cuenta, enviaremos un código."})

    gateway = IdentityServiceGateway(
        base_url="http://identity.test",
        transport=httpx.MockTransport(handle),
    )
    try:
        response = await gateway.solicitar_recuperacion_clave(
            b'{"correo":"ana@example.com"}'
        )
    finally:
        await gateway.aclose()

    assert response["mensaje"].startswith("Si existe una cuenta")


async def test_reenvia_confirmacion_de_recuperacion_a_identity():
    async def handle(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path.endswith("/clientes/recuperar-clave/confirmar")
        assert request.read() == (
            b'{"correo":"ana@example.com","codigo":"123456",'
            b'"nueva_clave":"NuevaClave123"}'
        )
        return httpx.Response(200, json={"mensaje": "Contraseña actualizada."})

    gateway = IdentityServiceGateway(
        base_url="http://identity.test",
        transport=httpx.MockTransport(handle),
    )
    try:
        response = await gateway.confirmar_recuperacion_clave(
            b'{"correo":"ana@example.com","codigo":"123456",'
            b'"nueva_clave":"NuevaClave123"}'
        )
    finally:
        await gateway.aclose()

    assert response["mensaje"] == "Contraseña actualizada."
