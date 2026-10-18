"""Agent nodes of the travel workflow.

Each node is a method so the LLM and tools are injected once, which lets tests
run the whole graph with fakes and no network access.
"""

import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.types import interrupt

from app.agents import prompts
from app.agents.airports import airport_label, metro_airports, resolve_iata
from app.agents.state import AGENT_ORDER, TravelState, empty_constraints
from app.agents.text import (
    compact_hotels,
    json_from_llm,
    route_departures,
    short_sentences,
    tool_text,
)
from app.agents.tools import TravelTools

logger = logging.getLogger(__name__)


# Tag for LLM calls whose tokens must not be streamed to the user (condensing).
INTERNAL_TAG = "tripmate:internal"

# Characters per token, a conservative estimate for English prose.
CHARS_PER_TOKEN = 4
# Room kept for the fixed instructions of the largest prompt template.
TEMPLATE_RESERVE_CHARS = 2500


class TravelAgents:
    def __init__(
        self,
        llm: BaseChatModel,
        tools: TravelTools,
        *,
        prompt_budget_tokens: int = 4000,
        max_continuations: int = 2,
    ):
        self.llm = llm
        self.tools = tools
        self.section_budget_chars = prompt_budget_tokens * CHARS_PER_TOKEN - TEMPLATE_RESERVE_CHARS
        self.max_continuations = max_continuations

    def _ask(self, system_prompt: str, user_prompt: str, *, internal: bool = False) -> str:
        """Ask the LLM and make sure the answer is complete.

        If the output hits the model's length limit, the model is asked to
        continue where it stopped, so answers are never returned cut off.
        `internal` calls are tagged so their tokens are never streamed to the UI.
        """
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
        config = {"tags": [INTERNAL_TAG]} if internal else None
        parts: list[str] = []

        for attempt in range(self.max_continuations + 1):
            response = self.llm.invoke(messages, config=config)
            text = str(response.content)
            parts.append(text)

            finish_reason = (getattr(response, "response_metadata", None) or {}).get(
                "finish_reason"
            )
            if finish_reason != "length" or attempt == self.max_continuations:
                if finish_reason == "length":
                    logger.warning("LLM answer still truncated after %d continuations", attempt)
                break

            logger.info("LLM answer hit the length limit, continuing (%d)", attempt + 1)
            messages = [
                *messages,
                AIMessage(content=text),
                HumanMessage(content=prompts.CONTINUE_PROMPT),
            ]

        return "".join(parts)

    def _condense(self, name: str, text: str, max_chars: int) -> str:
        return self._ask(
            prompts.CONDENSE_SYSTEM,
            prompts.CONDENSE_PROMPT.format(name=name, words=max(max_chars // 6, 60), text=text),
            internal=True,
        )

    def _fit(self, sections: dict[str, str], keep: tuple[str, ...] = ()) -> dict[str, str]:
        """Keep the prompt under budget without truncating anything.

        Small prompts pass through untouched. Otherwise the largest sections
        are condensed by the LLM (facts kept, whole sentences), sections in
        `keep` last.
        """
        fitted = {name: str(text or "").strip() for name, text in sections.items()}

        def total() -> int:
            return sum(len(text) for text in fitted.values())

        if total() <= self.section_budget_chars:
            return fitted

        order = sorted(fitted, key=lambda name: (name in keep, -len(fitted[name])))
        for name in order:
            excess = total() - self.section_budget_chars
            if excess <= 0:
                break

            target = max(len(fitted[name]) - excess, len(fitted[name]) // 3, 400)
            if target < len(fitted[name]):
                logger.info("Condensing %s section (%d chars)", name, len(fitted[name]))
                fitted[name] = self._condense(name, fitted[name], target)

        return fitted

    # Supervisor + input guardrail
    def supervisor(self, state: TravelState) -> dict[str, Any]:
        query = state["user_query"]
        llm_calls = state.get("llm_calls", 0)

        # Fail open on parser/model errors so a temporary JSON-format issue does
        # not block a valid travel request.
        try:
            guardrail = json_from_llm(
                self._ask(prompts.GUARDRAIL_SYSTEM, prompts.GUARDRAIL_PROMPT.format(query=query))
            )
            allowed = bool(guardrail.get("allowed", True))
            guardrail_reason = str(guardrail.get("reason", "")).strip()
            llm_calls += 1
        except ValueError as exc:
            logger.warning("Guardrail fallback used: %s", exc)
            allowed = True
            guardrail_reason = "Guardrail validation fallback allowed the request."

        if not allowed:
            reason = guardrail_reason or prompts.GUARDRAIL_BLOCKED_MESSAGE
            logger.info("Request blocked by guardrail: %s", reason)
            return {
                "guardrail_allowed": False,
                "guardrail_reason": reason,
                "selected_agents": [],
                "trip_constraints": empty_constraints(),
                "supervisor_reasoning": reason,
                "final_response": reason,
                "messages": [AIMessage(content=f"Guardrail blocked request: {reason}")],
                "llm_calls": llm_calls,
            }

        try:
            parsed = json_from_llm(
                self._ask(prompts.SUPERVISOR_SYSTEM, prompts.SUPERVISOR_PROMPT.format(query=query))
            )
            requested = parsed.get("selected_agents", [])
            selected = [name for name in AGENT_ORDER if name in requested]

            # The itinerary agent integrates whichever specialist results were selected.
            if "itinerary_agent" not in selected:
                selected.append("itinerary_agent")

            constraints = empty_constraints()
            if isinstance(parsed.get("trip_constraints"), dict):
                constraints.update(parsed["trip_constraints"])

            reasoning = str(parsed.get("reasoning", "")).strip()
            llm_calls += 1
        except ValueError as exc:
            logger.warning("Supervisor fallback used: %s", exc)
            selected = AGENT_ORDER.copy()
            constraints = empty_constraints()
            reasoning = (
                "Supervisor parsing failed, so the full travel workflow was selected "
                "as a safe fallback."
            )

        logger.info("Supervisor selected agents: %s", ", ".join(selected))
        return {
            "guardrail_allowed": True,
            "guardrail_reason": guardrail_reason,
            "selected_agents": selected,
            "trip_constraints": constraints,
            "supervisor_reasoning": reasoning,
            "messages": [AIMessage(content="Supervisor created the agent plan.")],
            "llm_calls": llm_calls,
        }

    def guardrail_blocked(self, state: TravelState) -> dict[str, Any]:
        reason = (
            state.get("final_response")
            or state.get("guardrail_reason")
            or "This request was blocked by the travel input guardrail."
        )
        return {"final_response": reason, "messages": [AIMessage(content=reason)]}

    # Specialists
    def _route(self, state: TravelState) -> tuple[str | None, str | None]:
        """Validated IATA codes for origin and destination (offline lookup)."""
        constraints = state.get("trip_constraints", {})
        origin = resolve_iata(constraints.get("origin_iata"), constraints.get("origin"))
        destination = resolve_iata(
            constraints.get("destination_iata"), constraints.get("destination")
        )
        return origin, destination

    def _live_departures(self, origin: str | None, destination: str | None) -> str:
        """Today's direct flights on the route, or a note explaining why there are none."""
        if not origin or not destination:
            return "None: the origin or destination airport could not be identified."

        # A live-data failure must not break the whole plan.
        try:
            flights = route_departures(
                self.tools.departures(origin), arrival_codes=metro_airports(destination)
            )
        except Exception as exc:
            logger.warning("Live flight lookup degraded: %s", exc)
            return "None: live flight data is unavailable right now."

        return flights or (
            f"None: no direct {origin} -> {destination} flight among today's departures "
            "(the route may require a connection)."
        )

    def flight_agent(self, state: TravelState) -> dict[str, Any]:
        origin, destination = self._route(state)
        live_flights = self._live_departures(origin, destination)

        route = (
            f"{airport_label(origin)} -> {airport_label(destination)}"
            if origin and destination
            else "Unknown: infer the most likely airports from the request."
        )

        flight_data = self._ask(
            prompts.FLIGHT_SYSTEM,
            prompts.FLIGHT_PROMPT.format(
                query=state["user_query"],
                constraints=state.get("trip_constraints", {}),
                route=route,
                live_flights=live_flights,
            ),
        )

        return {
            "flight_results": flight_data,
            "messages": [AIMessage(content="Flight recommendations generated.")],
            "llm_calls": state.get("llm_calls", 0) + 1,
        }

    def hotel_agent(self, state: TravelState) -> dict[str, Any]:
        destination = state.get("trip_constraints", {}).get("destination") or state["user_query"]

        try:
            hotel_results = compact_hotels(
                self.tools.search_hotels(f"Best hotels in {destination}")
            )
        except Exception as exc:
            logger.warning("Hotel agent degraded: %s", exc)
            hotel_results = "Hotel search is unavailable right now."

        return {
            "hotel_results": hotel_results,
            "messages": [AIMessage(content="Hotel information fetched.")],
        }

    def _destination(self, state: TravelState) -> tuple[str, int]:
        """Prefer the supervisor's extraction; only ask the LLM when it is missing."""
        destination = str(state.get("trip_constraints", {}).get("destination", "")).strip()

        if destination:
            return destination, 0

        response = self.llm.invoke(prompts.DESTINATION_PROMPT.format(query=state["user_query"]))
        return str(response.content).strip(), 1

    def weather_agent(self, state: TravelState) -> dict[str, Any]:
        llm_calls = state.get("llm_calls", 0)

        try:
            city, extra_calls = self._destination(state)
            llm_calls += extra_calls

            current = short_sentences(tool_text(self.tools.current_weather(city)), 800)
            forecast = short_sentences(tool_text(self.tools.forecast(city)), 1200)
            weather_results = f"Current Weather: {current}\nForecast: {forecast}"
        except Exception as exc:
            logger.warning("Weather agent degraded: %s", exc)
            weather_results = (
                "Weather data is unavailable right now; check a forecast before departure."
            )

        return {
            "weather_results": weather_results,
            "messages": [AIMessage(content="Weather information fetched.")],
            "llm_calls": llm_calls,
        }

    def _results(self, state: TravelState, *names: str) -> dict[str, str]:
        return {name: state.get(f"{name}_results", "") for name in names}

    def budget_agent(self, state: TravelState) -> dict[str, Any]:
        sections = self._fit(self._results(state, "flight", "hotel", "weather"))
        budget = self._ask(
            prompts.BUDGET_SYSTEM,
            prompts.BUDGET_PROMPT.format(
                query=state["user_query"],
                constraints=state.get("trip_constraints", {}),
                flights=sections["flight"],
                hotels=sections["hotel"],
                weather=sections["weather"],
            ),
        )

        return {
            "budget_results": budget,
            "messages": [AIMessage(content="Budget assessment generated.")],
            "llm_calls": state.get("llm_calls", 0) + 1,
        }

    def itinerary_agent(self, state: TravelState) -> dict[str, Any]:
        sections = self._fit(self._results(state, "flight", "hotel", "weather", "budget"))
        itinerary = self._ask(
            prompts.ITINERARY_SYSTEM,
            prompts.ITINERARY_PROMPT.format(
                query=state["user_query"],
                constraints=state.get("trip_constraints", {}),
                flights=sections["flight"],
                hotels=sections["hotel"],
                weather=sections["weather"],
                budget=sections["budget"],
            ),
        )

        return {
            "itinerary": itinerary,
            "approval_request": prompts.APPROVAL_REQUEST,
            "messages": [AIMessage(content="Draft itinerary created for human review.")],
            "llm_calls": state.get("llm_calls", 0) + 1,
        }

    # Human-in-the-loop
    def human_approval(self, state: TravelState) -> dict[str, Any]:
        # Never wrap interrupt() in try/except: LangGraph raises to pause the run.
        # On resume, the node restarts and interrupt() returns the resume value.
        review = interrupt(
            {
                "question": "Do you approve this itinerary?",
                "draft_itinerary": state.get("itinerary", ""),
                "approval_request": state.get("approval_request", ""),
            }
        )

        return {
            "approved": bool(review.get("approved", False)),
            "human_feedback": str(review.get("feedback", "")).strip(),
            "messages": [AIMessage(content="Human approval step completed.")],
        }

    def final_agent(self, state: TravelState) -> dict[str, Any]:
        if state.get("approved", False):
            review_instruction = prompts.FINAL_APPROVED_INSTRUCTION
        else:
            # The API already caps feedback at 2,000 characters.
            feedback = state.get("human_feedback", "").strip()
            review_instruction = prompts.FINAL_REVISION_INSTRUCTION.format(
                feedback=feedback or "Improve the draft before finalizing it."
            )

        sections = self._results(state, "flight", "hotel", "weather", "budget")
        sections["itinerary"] = state.get("itinerary", "")
        # The draft is what the user reviewed, so it is condensed only as a last resort.
        sections = self._fit(sections, keep=("itinerary",))

        final_response = self._ask(
            prompts.FINAL_SYSTEM,
            prompts.FINAL_PROMPT.format(
                review_instruction=review_instruction,
                query=state["user_query"],
                constraints=state.get("trip_constraints", {}),
                flights=sections["flight"],
                hotels=sections["hotel"],
                weather=sections["weather"],
                budget=sections["budget"],
                itinerary=sections["itinerary"],
            ),
        )

        return {
            "final_response": final_response,
            "messages": [AIMessage(content=final_response)],
            "llm_calls": state.get("llm_calls", 0) + 1,
        }
