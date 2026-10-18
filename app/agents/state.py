"""Shared LangGraph state and workflow constants."""

import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage


class TravelState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], operator.add]
    user_query: str

    # Supervisor + guardrail
    guardrail_allowed: bool
    guardrail_reason: str
    selected_agents: list[str]
    trip_constraints: dict[str, Any]
    supervisor_reasoning: str

    # Specialist results
    flight_results: str
    hotel_results: str
    weather_results: str
    budget_results: str
    itinerary: str

    # Human-in-the-loop
    approval_request: str
    approved: bool
    human_feedback: str
    final_response: str

    llm_calls: int


# Specialists always run in this order; the supervisor only chooses which ones.
SPECIALIST_AGENTS = ["flight_agent", "hotel_agent", "weather_agent", "budget_agent"]
AGENT_ORDER = [*SPECIALIST_AGENTS, "itinerary_agent"]

AGENT_LABELS = {
    "supervisor": "Supervisor",
    "guardrail_blocked": "Guardrail",
    "flight_agent": "Flight Agent",
    "hotel_agent": "Hotel Agent",
    "weather_agent": "Weather Agent",
    "budget_agent": "Budget Agent",
    "itinerary_agent": "Itinerary Agent",
    "human_approval": "Human Approval",
    "final_agent": "Final Agent",
}


def empty_constraints() -> dict[str, Any]:
    return {
        "destination": "",
        "origin": "",
        "destination_iata": "",
        "origin_iata": "",
        "duration": "",
        "budget": "",
        "travel_style": "",
        "special_preferences": [],
    }


def initial_state(user_query: str) -> TravelState:
    return {
        "messages": [HumanMessage(content=user_query)],
        "user_query": user_query,
        "guardrail_allowed": True,
        "guardrail_reason": "",
        "selected_agents": [],
        "trip_constraints": empty_constraints(),
        "supervisor_reasoning": "",
        "flight_results": "",
        "hotel_results": "",
        "weather_results": "",
        "budget_results": "",
        "itinerary": "",
        "approval_request": "",
        "approved": False,
        "human_feedback": "",
        "final_response": "",
        "llm_calls": 0,
    }
