"""Interface the agents use to reach external data.

The production implementation goes through MCP servers
(`app.integrations.mcp_toolbox.McpToolbox`); tests plug in an in-memory fake.
"""

from typing import Any, Protocol


class TravelTools(Protocol):
    def search_hotels(self, query: str) -> Any: ...

    def departures(self, airport_iata: str, limit: int = 100) -> Any: ...

    def current_weather(self, city: str) -> Any: ...

    def forecast(self, city: str) -> Any: ...
