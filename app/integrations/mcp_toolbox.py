"""MCP-backed implementation of the agents' tool interface.

Three MCP servers are used:
- Tavily (remote, streamable HTTP) for hotel search
- AviationStack (`uvx aviationstack-mcp`, stdio) for today's departure boards
- a custom OpenWeather server (`app/mcp_servers/weather_server.py`, stdio)

Graph nodes are synchronous and run in worker threads (FastAPI threadpool), while MCP clients
are async. The toolbox owns one event loop running in a background thread and submits every
call to it. Unlike `asyncio.run` per call, this also works when the caller already runs a loop
(async endpoint, `graph.ainvoke`, notebook), and a call that hangs is cut off by a timeout.
"""

import asyncio
import concurrent.futures
import logging
import os
import sys
import threading
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, TypeVar

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from app.core.config import Settings

logger = logging.getLogger(__name__)

WEATHER_SERVER_PATH = Path(__file__).resolve().parents[1] / "mcp_servers" / "weather_server.py"

T = TypeVar("T")


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
    def __init__(self, client: MultiServerMCPClient, timeout: float = 60.0):
        self._client = client
        self._timeout = timeout
        self._tools: dict[str, dict[str, BaseTool]] = {}
        self._lock = threading.Lock()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever, name="mcp-event-loop", daemon=True
        )
        self._thread.start()

    def _run(self, coro: Coroutine[Any, Any, T], what: str) -> T:
        """Run `coro` on the toolbox loop and wait for it, from any thread."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout=self._timeout)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise TimeoutError(f"MCP {what} did not answer within {self._timeout:g} s") from None

    def close(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)

    def _server_tools(self, server: str) -> dict[str, BaseTool]:
        # Each server is loaded on first use and independently, so one broken
        # server never prevents the others from working.
        with self._lock:
            if server not in self._tools:
                tools = self._run(self._client.get_tools(server_name=server), f"{server} server")
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

        return self._run(tool.ainvoke(args or {}), f"tool {tool_name}")

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
