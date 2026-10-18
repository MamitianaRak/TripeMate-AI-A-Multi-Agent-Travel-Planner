"""Use cases on top of the compiled graph: start a plan, resume it, stream steps."""

import logging
import uuid
from collections.abc import Iterator
from typing import Any

from langchain_core.messages import AIMessageChunk
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from app.agents.nodes import INTERNAL_TAG
from app.agents.state import AGENT_LABELS, initial_state
from app.core.errors import AppError, classify_provider_error

logger = logging.getLogger(__name__)

StepEvent = dict[str, Any]

# Nodes whose text the user reads; their tokens are streamed as they are generated.
STREAMED_NODES = {"itinerary_agent", "final_agent"}


def new_thread_id() -> str:
    return f"trip_{uuid.uuid4().hex}"


class TravelService:
    def __init__(self, graph: CompiledStateGraph):
        self.graph = graph

    @staticmethod
    def _config(thread_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}}

    def _pending_interrupt(self, thread_id: str) -> dict[str, Any] | None:
        snapshot = self.graph.get_state(self._config(thread_id))

        for task in snapshot.tasks:
            for pending in task.interrupts:
                value = pending.value
                return value if isinstance(value, dict) else {"value": value}

        return None

    def _result(self, thread_id: str) -> dict[str, Any]:
        values = self.graph.get_state(self._config(thread_id)).values
        pending = self._pending_interrupt(thread_id)
        draft = values.get("itinerary", "")

        return {
            "thread_id": thread_id,
            "status": "awaiting_approval" if pending else "completed",
            "requires_approval": pending is not None,
            "answer": draft if pending else (values.get("final_response") or draft),
            "approval_request": values.get("approval_request", ""),
            "itinerary": draft,
            "flight_results": values.get("flight_results", ""),
            "hotel_results": values.get("hotel_results", ""),
            "weather_results": values.get("weather_results", ""),
            "budget_results": values.get("budget_results", ""),
            "selected_agents": values.get("selected_agents", []),
            "trip_constraints": values.get("trip_constraints", {}),
            "supervisor_reasoning": values.get("supervisor_reasoning", ""),
            "guardrail_allowed": values.get("guardrail_allowed", True),
            "guardrail_reason": values.get("guardrail_reason", ""),
            "approved": values.get("approved") if not pending else None,
            "human_feedback": values.get("human_feedback", ""),
            "llm_calls": values.get("llm_calls", 0),
        }

    def _ensure_awaiting_approval(self, thread_id: str) -> None:
        snapshot = self.graph.get_state(self._config(thread_id))

        if not snapshot.values:
            raise AppError(404, "thread_not_found", "No travel plan exists for this thread_id.")

        if self._pending_interrupt(thread_id) is None:
            raise AppError(
                409, "no_pending_approval", "This travel plan is not waiting for approval."
            )

    @staticmethod
    def _resume_command(approved: bool, feedback: str) -> Command:
        return Command(resume={"approved": approved, "feedback": feedback.strip()})

    def _invoke(self, graph_input: Any, thread_id: str) -> None:
        try:
            self.graph.invoke(graph_input, config=self._config(thread_id))
        except Exception as exc:
            # Turn provider failures (rate limit, timeout) into clear client errors.
            classified = classify_provider_error(exc)
            if classified is None:
                raise
            logger.warning("Provider failure on %s: %s", thread_id, exc)
            raise classified from exc

    # Blocking API
    def start(self, message: str, thread_id: str | None = None) -> dict[str, Any]:
        thread_id = thread_id or new_thread_id()
        logger.info("Starting travel plan %s", thread_id)
        self._invoke(initial_state(message), thread_id)
        return self._result(thread_id)

    def resume(self, thread_id: str, approved: bool, feedback: str = "") -> dict[str, Any]:
        self._ensure_awaiting_approval(thread_id)
        logger.info("Resuming travel plan %s (approved=%s)", thread_id, approved)
        self._invoke(self._resume_command(approved, feedback), thread_id)
        return self._result(thread_id)

    # Streaming API: yields one "step" event per finished node, then the result
    @staticmethod
    def _token_event(message: Any, metadata: dict[str, Any]) -> StepEvent | None:
        """A `token` event for user-facing text, or None for anything else."""
        node = metadata.get("langgraph_node")

        if (
            node not in STREAMED_NODES
            or not isinstance(message, AIMessageChunk)
            or INTERNAL_TAG in (metadata.get("tags") or [])
            or not isinstance(message.content, str)
            or not message.content
        ):
            return None

        return {"event": "token", "data": {"node": node, "text": message.content}}

    def _step_events(self, update: dict[str, Any], thread_id: str) -> Iterator[StepEvent]:
        for node, payload in update.items():
            if node == "__interrupt__":
                continue

            event: StepEvent = {
                "node": node,
                "label": AGENT_LABELS.get(node, node),
                "thread_id": thread_id,
            }

            if node == "supervisor" and isinstance(payload, dict):
                event["selected_agents"] = payload.get("selected_agents", [])
                event["supervisor_reasoning"] = payload.get("supervisor_reasoning", "")
                event["guardrail_allowed"] = payload.get("guardrail_allowed", True)

            yield {"event": "step", "data": event}

    def _stream(self, graph_input: Any, thread_id: str) -> Iterator[StepEvent]:
        """Yield `step` events as agents finish, `token` events while the draft
        and the final plan are being written, then the `result`."""
        for mode, chunk in self.graph.stream(
            graph_input,
            config=self._config(thread_id),
            stream_mode=["updates", "messages"],
        ):
            if mode == "messages":
                token = self._token_event(*chunk)
                if token:
                    yield token
            else:
                yield from self._step_events(chunk, thread_id)

        yield {"event": "result", "data": self._result(thread_id)}

    def stream_start(self, message: str, thread_id: str | None = None) -> Iterator[StepEvent]:
        thread_id = thread_id or new_thread_id()
        logger.info("Streaming travel plan %s", thread_id)
        return self._stream(initial_state(message), thread_id)

    def stream_resume(
        self, thread_id: str, approved: bool, feedback: str = ""
    ) -> Iterator[StepEvent]:
        # Validate before streaming so errors surface as a normal HTTP status.
        self._ensure_awaiting_approval(thread_id)
        logger.info("Streaming resume of %s (approved=%s)", thread_id, approved)
        return self._stream(self._resume_command(approved, feedback), thread_id)

    def check_database(self) -> None:
        """Raise if the checkpointer cannot be read."""
        self.graph.get_state(self._config("healthcheck"))
