"""Token streaming: the draft and the final plan reach the UI while they are written."""

import json

from langgraph.checkpoint.memory import MemorySaver

from app.agents.graph import build_travel_graph
from app.services.travel_service import TravelService
from tests.fakes import FakeLLM, FakeTools


def _tokens(events, node):
    return [
        e["data"]["text"] for e in events if e["event"] == "token" and e["data"]["node"] == node
    ]


def test_draft_tokens_stream_before_the_result(service):
    events = list(service.stream_start("Plan 3 days in Tokyo"))
    kinds = [event["event"] for event in events]
    draft_tokens = _tokens(events, "itinerary_agent")

    assert len(draft_tokens) > 1
    # Tokens arrive before the itinerary step completes, and before the result.
    first_token = kinds.index("token")
    itinerary_step = next(
        i
        for i, e in enumerate(events)
        if e["event"] == "step" and e["data"]["node"] == "itinerary_agent"
    )
    assert first_token < itinerary_step < kinds.index("result")
    # Concatenated tokens are exactly the stored draft.
    assert "".join(draft_tokens) == events[-1]["data"]["itinerary"]


def test_only_user_facing_agents_stream_tokens(service):
    events = list(service.stream_start("Plan 3 days in Tokyo"))
    streamed_nodes = {e["data"]["node"] for e in events if e["event"] == "token"}

    # Supervisor JSON, flight and budget analyses are not streamed as text.
    assert streamed_nodes == {"itinerary_agent"}


def test_final_plan_tokens_stream_on_resume(service):
    thread_id = list(service.stream_start("Plan 3 days in Tokyo"))[-1]["data"]["thread_id"]
    events = list(service.stream_resume(thread_id, approved=True))

    assert "".join(_tokens(events, "final_agent")) == "FINAL PLAN (approved)"
    assert events[-1]["data"]["answer"] == "FINAL PLAN (approved)"


class VerboseHotelTools(FakeTools):
    """Five long hotel descriptions, enough to exceed a small prompt budget."""

    def search_hotels(self, query: str):
        self._record("search_hotels")
        content = "Quiet rooms near the station with breakfast included. " * 10
        results = [
            {"title": f"Hotel {index}", "url": f"https://h/{index}", "content": content}
            for index in range(5)
        ]
        return json.dumps({"results": results})


def test_condensing_calls_are_not_streamed():
    llm = FakeLLM()
    # A tiny budget forces the agents to condense the hotel section first.
    graph = build_travel_graph(llm, VerboseHotelTools(), MemorySaver(), prompt_budget_tokens=700)
    events = list(TravelService(graph).stream_start("Plan 3 days in Tokyo"))

    assert any("Condense the following" in prompt for prompt in llm.prompts)
    # Only the draft's own tokens reach the UI, not the condensed text ("ok").
    assert "".join(_tokens(events, "itinerary_agent")) == events[-1]["data"]["itinerary"]
