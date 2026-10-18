"""Network-free stand-ins for the LLM and the MCP tools."""

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import Field


def _prompt_text(messages: list[BaseMessage]) -> str:
    return "\n".join(str(message.content) for message in messages)


class FakeLLM(BaseChatModel):
    """A real LangChain chat model that answers by recognizing the agent prompt.

    It streams its answer word by word when LangGraph asks for tokens, exactly
    like ChatGroq, so the token-streaming path is tested end to end.
    """

    allowed: bool = True
    selected_agents: list[str] = Field(
        default_factory=lambda: ["flight_agent", "hotel_agent", "weather_agent", "budget_agent"]
    )
    destination: str = "Tokyo"
    supervisor_reply: str | None = None
    fail_with: Any = None
    prompts: list[str] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "fake-travel-llm"

    def _answer(self, messages: list[BaseMessage]) -> str:
        if self.fail_with is not None:
            raise self.fail_with
        prompt = _prompt_text(messages)
        self.prompts.append(prompt)
        return self._reply(prompt)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        message = AIMessage(
            content=self._answer(messages), response_metadata={"finish_reason": "stop"}
        )
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _stream(self, messages, stop=None, run_manager=None, **kwargs) -> Iterator:
        for piece in re.findall(r"\S+\s*", self._answer(messages)):
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=piece))
            if run_manager:
                run_manager.on_llm_new_token(piece, chunk=chunk)
            yield chunk

    def _reply(self, prompt: str) -> str:
        if "input guardrail" in prompt:
            reason = "" if self.allowed else "Not a travel request."
            return json.dumps({"allowed": self.allowed, "reason": reason})

        if "supervisor of a multi-agent" in prompt:
            if self.supervisor_reply is not None:
                return self.supervisor_reply
            return json.dumps(
                {
                    "selected_agents": self.selected_agents,
                    "trip_constraints": {
                        "destination": self.destination,
                        "origin": "Dhaka",
                        "destination_iata": "NRT",
                        "origin_iata": "DAC",
                        "duration": "3 days",
                    },
                    "reasoning": "Selected agents for the trip.",
                }
            )

        if "Extract only the destination" in prompt:
            return self.destination
        if "travel flight expert" in prompt:
            return "Fly DAC to NRT with a stop, about 9 hours."
        if "realistic for the user's budget" in prompt:
            return "- Budget is feasible."
        if "Create a complete travel itinerary" in prompt:
            return "Day 1: Arrive. Day 2: Explore. Day 3: Depart."
        if "Generate the final travel response" in prompt:
            if "requested a revision" in prompt:
                return "FINAL PLAN (revised)"
            return "FINAL PLAN (approved)"

        return "ok"


def departure(flight_number: str, airline: str, arrival: str, dep: str, arr: str) -> dict:
    """One row of the AviationStack MCP departure board."""
    return {
        "airline": airline,
        "flight_number": flight_number,
        "departure_scheduled_time": f"2026-10-18T{dep}:00.000",
        "arrival_scheduled_time": f"2026-10-18T{arr}:00.000",
        "arrival_airport_code": arrival,
    }


# Today's DAC departure board: two Tokyo flights (NRT and HND), a codeshare
# duplicate of the first one, and a flight to another city.
DEPARTURES = [
    departure("BG376", "Biman Bangladesh", "NRT", "10:00", "19:30"),
    departure("NH5001", "ANA", "NRT", "10:00", "19:30"),
    departure("EK585", "Emirates", "DXB", "11:15", "14:30"),
    departure("JL052", "Japan Airlines", "HND", "22:40", "07:55"),
]


@dataclass
class FakeTools:
    fail: set[str] = field(default_factory=set)
    calls: list[str] = field(default_factory=list)

    def _record(self, name: str) -> None:
        self.calls.append(name)
        if name in self.fail:
            raise RuntimeError(f"{name} is down")

    def search_hotels(self, query: str) -> Any:
        self._record("search_hotels")
        payload = {
            "results": [
                {
                    "title": "Hotel Sakura",
                    "url": "https://example.com/a",
                    "content": "Near Shinjuku.",
                }
            ]
        }
        return [{"type": "text", "text": json.dumps(payload)}]

    def departures(self, airport_iata: str, limit: int = 100) -> Any:
        self._record("departures")
        return json.dumps({"ok": True, "count": len(DEPARTURES), "data": DEPARTURES})

    def current_weather(self, city: str) -> Any:
        self._record("current_weather")
        return {"city": city, "temperature_c": 21}

    def forecast(self, city: str) -> Any:
        self._record("forecast")
        return {"city": city, "forecast": [{"temperature": 20}]}
