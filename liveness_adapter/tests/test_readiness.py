import asyncio

import pytest

from src import main
from src.infrastructure.provider_factory import LivenessProviderFactory
from src.infrastructure.providers.propio import PropioProvider

READY = "/api/v1/liveness-adapter/ready"
HEALTH = "/api/v1/liveness-adapter/health"


class FakeRedis:
    async def ping(self):
        return True


class FakeAnalyzer:
    def __init__(self, fails=False):
        self.fails = fails
        self.loaded = 0

    def warm_up(self):
        if self.fails:
            raise RuntimeError("Modelo facial no disponible.")
        self.loaded += 1


@pytest.fixture
def warm_state(monkeypatch):
    monkeypatch.setattr(main, "_providers_warm", asyncio.Event())
    monkeypatch.setattr(main, "_redis", FakeRedis())


async def test_no_esta_listo_hasta_cargar_el_modelo(client, warm_state, monkeypatch):
    analyzer = FakeAnalyzer()
    monkeypatch.setattr(main, "_factory", LivenessProviderFactory([PropioProvider(analyzer)]))

    assert (await client.get(READY)).status_code == 503
    assert (await client.get(HEALTH)).status_code == 200

    await main.warm_up_providers()

    assert analyzer.loaded == 1
    assert (await client.get(READY)).status_code == 200


async def test_si_el_modelo_no_carga_sigue_sin_estar_listo(client, warm_state, monkeypatch):
    monkeypatch.setattr(main, "_factory", LivenessProviderFactory([PropioProvider(FakeAnalyzer(fails=True))]))

    await main.warm_up_providers()

    assert (await client.get(READY)).status_code == 503
    assert (await client.get(HEALTH)).status_code == 200
