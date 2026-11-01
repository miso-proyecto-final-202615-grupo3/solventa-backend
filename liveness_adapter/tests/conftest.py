import pytest
from httpx import ASGITransport, AsyncClient

import src.main as main
from src.application.ports import ProviderSessionStarted, ProviderUnavailableError, ProviderVerificationResult
from src.infrastructure.configuration import InMemoryActiveProviderConfiguration
from src.infrastructure.provider_factory import LivenessProviderFactory


class InMemorySessionStore:
    def __init__(self):
        self.values: dict[str, dict] = {}
        self.fail = False

    async def save(self, session_id, session):
        if self.fail:
            raise ConnectionError("redis caído")
        self.values[session_id] = dict(session)

    async def get(self, session_id):
        if self.fail:
            raise ConnectionError("redis caído")
        value = self.values.get(session_id)
        return dict(value) if value else None

    async def transition(self, session_id, expected, target):
        if self.fail:
            raise ConnectionError("redis caído")
        value = self.values.get(session_id)
        if value is None or value["state"] != expected:
            return False
        value["state"] = target
        return True


class AsyncActiveProvider(InMemoryActiveProviderConfiguration):
    async def get_active_provider_async(self):
        return self.get_active_provider()

    async def set_active_provider_async(self, name):
        self.set_active_provider(name)


class FakeFramesProvider:
    name = "propio"
    capture_type = "FRAMES"
    requires_budget = False

    def __init__(self, approved=True, unavailable=False):
        self.approved = approved
        self.unavailable = unavailable
        self.verifications = 0

    def start_session(self, customer_id, session_id):
        return ProviderSessionStarted(capture={"tipo": "FRAMES", "reto": {"gesto": "BLINK", "nonce": "nonce-1"}})

    def verify(self, session, frames, sdk_result=None):
        self.verifications += 1
        if self.unavailable:
            raise ProviderUnavailableError()
        return ProviderVerificationResult("propio-1" if self.approved else "", self.approved, None if self.approved else "GESTO_NO_DETECTADO")


class FakeSdkProvider:
    name = "didit"
    capture_type = "SDK"
    requires_budget = True

    def __init__(self, approved=True):
        self.approved = approved
        self.started = 0

    def start_session(self, customer_id, session_id):
        self.started += 1
        return ProviderSessionStarted(
            capture={"tipo": "SDK", "sdk": {"nombre": "DIDIT", "session_token": "token"}},
            provider_session_id="didit-session",
        )

    def verify(self, session, frames, sdk_result=None):
        return ProviderVerificationResult("didit-session", self.approved, None if self.approved else "PRUEBA_VIDA_FALLIDA")


class FakeBudget:
    def __init__(self, allowed=True):
        self.allowed = allowed

    async def consume(self, provider_name, now=None):
        return self.allowed


@pytest.fixture
def adapter(monkeypatch):
    store = InMemorySessionStore()
    propio = FakeFramesProvider()
    didit = FakeSdkProvider()
    active = AsyncActiveProvider("propio")
    budget = FakeBudget()
    monkeypatch.setattr(main, "_session_store", store)
    monkeypatch.setattr(main, "_factory", LivenessProviderFactory([propio, didit]))
    monkeypatch.setattr(main, "_active_provider", active)
    monkeypatch.setattr(main, "_budget", budget)
    monkeypatch.setattr(main.settings, "ADMIN_TOKEN", "secreto")
    return {"store": store, "propio": propio, "didit": didit, "active": active, "budget": budget}


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as http:
        yield http
