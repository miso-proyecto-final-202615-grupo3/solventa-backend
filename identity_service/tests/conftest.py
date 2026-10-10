from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client
