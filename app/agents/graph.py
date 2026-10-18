"""LangGraph workflow: supervisor -> selected specialists -> draft -> approval -> final."""

from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.nodes import TravelAgents
from app.agents.state import AGENT_ORDER, SPECIALIST_AGENTS, TravelState
from app.agents.tools import TravelTools

ROUTE_MAP = {name: name for name in ["guardrail_blocked", *AGENT_ORDER]}


def _selected(state: TravelState) -> list[str]:
    selected = state.get("selected_agents", [])
    return [agent for agent in AGENT_ORDER if agent in selected]


def route_from_supervisor(state: TravelState) -> str:
    if not state.get("guardrail_allowed", True):
        return "guardrail_blocked"

    selected = _selected(state)
    return selected[0] if selected else "itinerary_agent"


def route_after(current_agent: str):
    def route(state: TravelState) -> str:
        selected = _selected(state)
        current_index = AGENT_ORDER.index(current_agent)

        for next_agent in AGENT_ORDER[current_index + 1 :]:
            if next_agent in selected:
                return next_agent

        return "itinerary_agent"

    return route


def build_travel_graph(
    llm: BaseChatModel,
    tools: TravelTools,
    checkpointer: BaseCheckpointSaver,
    *,
    prompt_budget_tokens: int = 4000,
    max_continuations: int = 2,
) -> CompiledStateGraph:
    agents = TravelAgents(
        llm,
        tools,
        prompt_budget_tokens=prompt_budget_tokens,
        max_continuations=max_continuations,
    )
    graph = StateGraph(TravelState)

    graph.add_node("supervisor", agents.supervisor)
    graph.add_node("guardrail_blocked", agents.guardrail_blocked)
    graph.add_node("flight_agent", agents.flight_agent)
    graph.add_node("hotel_agent", agents.hotel_agent)
    graph.add_node("weather_agent", agents.weather_agent)
    graph.add_node("budget_agent", agents.budget_agent)
    graph.add_node("itinerary_agent", agents.itinerary_agent)
    graph.add_node("human_approval", agents.human_approval)
    graph.add_node("final_agent", agents.final_agent)

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges("supervisor", route_from_supervisor, ROUTE_MAP)

    for agent in SPECIALIST_AGENTS:
        graph.add_conditional_edges(agent, route_after(agent), ROUTE_MAP)

    graph.add_edge("itinerary_agent", "human_approval")
    graph.add_edge("human_approval", "final_agent")
    graph.add_edge("final_agent", END)
    graph.add_edge("guardrail_blocked", END)

    return graph.compile(checkpointer=checkpointer)
