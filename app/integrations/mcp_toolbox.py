"""MCP-backed implementation of the agents' tool interface.

Three MCP servers are used:
- Tavily (remote, streamable HTTP) for hotel search
- AviationStack (`uvx aviationstack-mcp`, stdio) for today's departure boards
- a custom OpenWeather server (`app/mcp_servers/weather_server.py`, stdio)

Graph nodes are synchronous and run in worker threads (FastAPI threadpool),
so each call drives its own event loop with `asyncio.run`.
"""

import asyncio
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from app.core.config import Settings

logger = logging.getLogger(__name__)

WEATHER_SERVER_PATH = Path(__file__).resolve().parents[1] / "mcp_servers" / "weather_server.py"


def build_mcp_client(settings: Settings) -> MultiServerMCPClient:
    aviation_env = {**os.environ, "AVIATION_STACK_API_KEY": settings.aviationstack_api_key}
    weather_env = {**os.environ, "OPENWEATHER_API_KEY": settings.openweather_api_key}

    return MultiServerMCPClient(
        {
            "tavily": {
                "transport": "streamable_http",
                "url": f"https://mcp.tavily.com/mcp/?tavilyApiKey={settings.tavily_api_key}",
            },
            "aviationstack": {
                "transport": "stdio",
                "command": "uvx",
                "args": ["aviationstack-mcp"],
                "env": aviation_env,
            },
            "weather": {
                "transport": "stdio",
                "command": sys.executable,
                "args": [str(WEATHER_SERVER_PATH)],
                "env": weather_env,
            },
        }
    )


class McpToolbox:
    def __init__(self, client: MultiServerMCPClient):
        self._client = client
        self._tools: dict[str, dict[str, BaseTool]] = {}
        self._lock = threading.Lock()

    def _server_tools(self, server: str) -> dict[str, BaseTool]:
        # Each server is loaded on first use and independently, so one broken
        # server never prevents the others from working.
        with self._lock:
            if server not in self._tools:
                tools = asyncio.run(self._client.get_tools(server_name=server))
                self._tools[server] = {tool.name: tool for tool in tools}
                logger.info("Loaded %d tools from %s MCP server", len(tools), server)

            return self._tools[server]

    def _call(self, server: str, tool_name: str, args: dict[str, Any] | None = None) -> Any:
        tools = self._server_tools(server)
        tool = tools.get(tool_name)

        if tool is None:
            available = ", ".join(sorted(tools)) or "none"
            raise RuntimeError(
                f"MCP tool '{tool_name}' not found on {server} server. Available: {available}"
            )

        return asyncio.run(tool.ainvoke(args or {}))

    def search_hotels(self, query: str) -> Any:
        return self._call("tavily", "tavily_search", {"query": query})

    def departures(self, airport_iata: str, limit: int = 100) -> Any:
        return self._call(
            "aviationstack",
            "flight_arrival_departure_schedule",
            {
                "airport_iata_code": airport_iata,
                "schedule_type": "departure",
                "number_of_flights": limit,
            },
        )

    def current_weather(self, city: str) -> Any:
        return self._call("weather", "get_current_weather", {"city": city})

    def forecast(self, city: str) -> Any:
        return self._call("weather", "get_forecast", {"city": city})
