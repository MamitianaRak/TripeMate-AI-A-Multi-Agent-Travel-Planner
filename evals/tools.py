"""Tools for the trajectory evaluation.

`StubTools` answers like the MCP servers with fixed data, so a run measures the agents' decisions
without spending the AviationStack free plan (100 requests a month) or Tavily credits.
`RecordingTools` wraps any implementation and records which tools the agents called.
"""

import json
from typing import Any

from app.agents.tools import TravelTools


class StubTools:
    def search_hotels(self, query: str) -> Any:
        payload = {
            "results": [
                {
                    "title": f"Central boutique hotel ({query})",
                    "url": "https://example.com/hotel",
                    "content": "Quiet street near the old town, from 95 EUR a night.",
                }
            ]
        }
        return [{"type": "text", "text": json.dumps(payload)}]

    def departures(self, airport_iata: str, limit: int = 100) -> Any:
        # No route filter here: the flight agent keeps only flights to the destination,
        # so with this board most routes honestly report "no direct flight today".
        board = [
            {
                "airline": "Example Air",
                "flight_number": "EX101",
                "departure_scheduled_time": "2026-10-18T09:00:00.000",
                "arrival_scheduled_time": "2026-10-18T12:00:00.000",
                "arrival_airport_code": "BCN",
            }
        ]
        return json.dumps({"ok": True, "count": len(board), "data": board})

    def current_weather(self, city: str) -> Any:
        return {"city": city, "temperature_c": 18, "description": "partly cloudy"}

    def forecast(self, city: str) -> Any:
        return {"city": city, "forecast": [{"day": 1, "temperature": 19, "rain_mm": 2}]}


class RecordingTools:
    def __init__(self, inner: TravelTools):
        self.inner = inner
        self.calls: list[str] = []

    def search_hotels(self, query: str) -> Any:
        self.calls.append("search_hotels")
        return self.inner.search_hotels(query)

    def departures(self, airport_iata: str, limit: int = 100) -> Any:
        self.calls.append("departures")
        return self.inner.departures(airport_iata, limit)

    def current_weather(self, city: str) -> Any:
        self.calls.append("current_weather")
        return self.inner.current_weather(city)

    def forecast(self, city: str) -> Any:
        self.calls.append("forecast")
        return self.inner.forecast(city)
