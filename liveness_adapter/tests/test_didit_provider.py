import json

import httpx
import pytest

from src.application.ports import ProviderUnavailableError
from src.infrastructure.budget import ProviderBudget
from src.infrastructure.providers.didit import DiditProvider


def _provider(handler):
    return DiditProvider("https://didit.test", "api-key", "workflow-1", transport=httpx.MockTransport(handler))


def test_crea_sesion_con_el_contrato_de_didit():
    seen = {}

    def handler(request):
        seen["key"] = request.headers["x-api-key"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"session_id": "didit-1", "session_token": "token-1"})

    started = _provider(handler).start_session("cliente-1", "sesion-1")

    assert seen["key"] == "api-key"
    assert seen["body"]["workflow_id"] == "workflow-1"
    assert seen["body"]["vendor_data"] == "cliente-1"
    assert started.capture == {"tipo": "SDK", "sdk": {"nombre": "DIDIT", "session_token": "token-1"}}
    assert started.provider_session_id == "didit-1"


@pytest.mark.parametrize("status, approved, reason", [("Approved", True, None), ("Declined", False, "PRUEBA_VIDA_FALLIDA")])
def test_traduce_la_decision(status, approved, reason):
    provider = _provider(lambda request: httpx.Response(200, json={"status": status}))

    result = provider.verify({"provider_session_id": "didit-1"}, {}, "COMPLETED")

    assert result.approved is approved
    assert result.reason == reason


@pytest.mark.parametrize(
    "response",
    [httpx.Response(200, json={"status": "In Review"}), httpx.Response(400, json={}), httpx.Response(429), httpx.Response(503)],
)
def test_estados_pendientes_o_errores_no_consumen_intento(response):
    provider = _provider(lambda request: response)

    with pytest.raises(ProviderUnavailableError):
        provider.verify({"provider_session_id": "didit-1"}, {}, "COMPLETED")


class FakePipeline:
    def __init__(self, redis):
        self.redis = redis
        self.ops = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def incr(self, key):
        self.ops.append(("incr", key))

    def expire(self, key, seconds):
        self.ops.append(("expire", key))

    async def execute(self):
        if self.redis.fail:
            raise ConnectionError()
        results = []
        for op, key in self.ops:
            if op == "incr":
                self.redis.counts[key] = self.redis.counts.get(key, 0) + 1
                results.append(self.redis.counts[key])
            else:
                results.append(True)
        return results


class FakeRedis:
    def __init__(self):
        self.counts = {}
        self.fail = False

    def pipeline(self, transaction=True):
        return FakePipeline(self)


async def test_tope_diario_limita_el_uso():
    budget = ProviderBudget(FakeRedis(), max_per_day=2, max_per_month=100)

    results = [await budget.consume("didit") for _ in range(3)]

    assert results == [True, True, False]


async def test_sin_redis_no_se_gasta():
    redis = FakeRedis()
    redis.fail = True

    assert await ProviderBudget(redis, 5, 100).consume("didit") is False
