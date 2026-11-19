from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.presentation.dependencies import require_cliente


@pytest.fixture
def cliente_autenticado():
    app.dependency_overrides[require_cliente] = lambda: "cliente-test"
    yield
    app.dependency_overrides.pop(require_cliente, None)


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client