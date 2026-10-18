import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver

from app.agents.graph import build_travel_graph
from app.core.config import Settings
from app.main import create_app
from app.services.travel_service import TravelService
from tests.fakes import FakeLLM, FakeTools


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    """Keep real keys from the developer's shell out of the tests."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def tools() -> FakeTools:
    return FakeTools()


@pytest.fixture
def service(llm: FakeLLM, tools: FakeTools) -> TravelService:
    graph = build_travel_graph(llm=llm, tools=tools, checkpointer=MemorySaver())
    return TravelService(graph)


@pytest.fixture
def settings() -> Settings:
    # _env_file=None keeps a developer's local .env out of the tests.
    return Settings(_env_file=None, rate_limit_requests=100, environment="test")


@pytest.fixture
def client(settings: Settings, service: TravelService):
    with TestClient(create_app(settings=settings, travel_service=service)) as test_client:
        yield test_client
