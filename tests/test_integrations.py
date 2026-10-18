"""MCP toolbox and custom weather server, with the network mocked out."""

from types import SimpleNamespace

import pytest

from app.integrations.mcp_toolbox import McpToolbox
from app.mcp_servers import weather_server


class FakeTool:
    def __init__(self, name: str):
        self.name = name
        self.received: list[dict] = []

    async def ainvoke(self, args: dict):
        self.received.append(args)
        return f"{self.name} result"


class FakeMcpClient:
    def __init__(self, servers: dict[str, list[FakeTool]]):
        self.servers = servers
        self.loads: list[str] = []

    async def get_tools(self, server_name: str):
        self.loads.append(server_name)
        if server_name not in self.servers:
            raise ConnectionError(f"{server_name} unreachable")
        return self.servers[server_name]


def test_toolbox_calls_tools_and_caches_each_server():
    search = FakeTool("tavily_search")
    client = FakeMcpClient({"tavily": [search]})
    toolbox = McpToolbox(client)

    assert toolbox.search_hotels("Tokyo") == "tavily_search result"
    toolbox.search_hotels("Paris")

    assert search.received == [{"query": "Tokyo"}, {"query": "Paris"}]
    assert client.loads == ["tavily"]


def test_toolbox_reports_missing_tool():
    toolbox = McpToolbox(FakeMcpClient({"weather": [FakeTool("get_forecast")]}))

    with pytest.raises(RuntimeError, match="get_current_weather"):
        toolbox.current_weather("Tokyo")


def test_one_broken_server_does_not_affect_others():
    toolbox = McpToolbox(FakeMcpClient({"weather": [FakeTool("get_forecast")]}))

    with pytest.raises(ConnectionError):
        toolbox.departures("DAC")
    assert toolbox.forecast("Tokyo") == "get_forecast result"


def test_departures_requests_the_free_plan_timetable_tool():
    board = FakeTool("flight_arrival_departure_schedule")
    toolbox = McpToolbox(FakeMcpClient({"aviationstack": [board]}))

    toolbox.departures("DAC")

    assert board.received == [
        {"airport_iata_code": "DAC", "schedule_type": "departure", "number_of_flights": 100}
    ]


def _fake_response(status: int, payload: dict):
    return SimpleNamespace(status_code=status, json=lambda: payload)


def test_weather_server_formats_current_weather(monkeypatch):
    payload = {
        "name": "Tokyo",
        "main": {"temp": 21, "feels_like": 20, "humidity": 60},
        "weather": [{"description": "clear sky"}],
        "wind": {"speed": 3},
    }
    monkeypatch.setenv("OPENWEATHER_API_KEY", "key")
    monkeypatch.setattr(
        weather_server.requests, "get", lambda *a, **k: _fake_response(200, payload)
    )

    result = weather_server.get_current_weather("Tokyo")
    assert result["temperature_c"] == 21
    assert result["condition"] == "clear sky"


def test_weather_server_returns_error_instead_of_crashing(monkeypatch):
    monkeypatch.setenv("OPENWEATHER_API_KEY", "key")
    monkeypatch.setattr(
        weather_server.requests,
        "get",
        lambda *a, **k: _fake_response(404, {"message": "city not found"}),
    )

    assert weather_server.get_forecast("Nowhere") == {"error": "city not found", "city": "Nowhere"}


def test_weather_server_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENWEATHER_API_KEY", raising=False)
    assert "error" in weather_server.get_current_weather("Tokyo")
