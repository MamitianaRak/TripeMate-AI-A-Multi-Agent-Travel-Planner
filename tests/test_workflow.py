"""End-to-end graph behavior with a fake LLM and fake MCP tools."""

import pytest

from app.core.errors import AppError
from tests.fakes import FakeLLM, FakeTools


def test_plan_pauses_for_approval_with_draft(service):
    result = service.start("Plan 3 days in Tokyo")

    assert result["status"] == "awaiting_approval"
    assert result["requires_approval"] is True
    assert result["answer"].startswith("Day 1")
    assert result["selected_agents"][-1] == "itinerary_agent"
    assert "Hotel Sakura" in result["hotel_results"]


def test_approval_generates_final_plan(service):
    thread_id = service.start("Plan 3 days in Tokyo")["thread_id"]
    result = service.resume(thread_id, approved=True)

    assert result["status"] == "completed"
    assert result["answer"] == "FINAL PLAN (approved)"
    assert result["approved"] is True


def test_revision_feedback_reaches_final_agent(service, llm: FakeLLM):
    thread_id = service.start("Plan 3 days in Tokyo")["thread_id"]
    result = service.resume(thread_id, approved=False, feedback="Add more food spots")

    assert result["answer"] == "FINAL PLAN (revised)"
    assert result["human_feedback"] == "Add more food spots"
    assert "Add more food spots" in llm.prompts[-1]


def test_guardrail_blocks_off_topic_request(llm: FakeLLM, tools: FakeTools, service):
    llm.allowed = False
    result = service.start("Write my math homework")

    assert result["status"] == "completed"
    assert result["guardrail_allowed"] is False
    assert result["answer"] == "Not a travel request."
    assert tools.calls == []


def test_supervisor_runs_only_selected_agents(llm: FakeLLM, tools: FakeTools, service):
    llm.selected_agents = ["hotel_agent"]
    result = service.start("Find a hotel in Tokyo")

    assert result["selected_agents"] == ["hotel_agent", "itinerary_agent"]
    assert tools.calls == ["search_hotels"]


def test_supervisor_parse_failure_falls_back_to_full_workflow(llm: FakeLLM, service):
    llm.supervisor_reply = "not json"
    result = service.start("Plan a trip")

    assert result["selected_agents"] == [
        "flight_agent",
        "hotel_agent",
        "weather_agent",
        "budget_agent",
        "itinerary_agent",
    ]


def test_weather_uses_supervisor_destination_without_extra_llm_call(llm: FakeLLM, service):
    service.start("Plan 3 days in Tokyo")
    assert not any("Extract only the destination" in prompt for prompt in llm.prompts)


def _flight_prompt(llm: FakeLLM) -> str:
    return next(prompt for prompt in llm.prompts if "travel flight expert" in prompt)


def test_failing_mcp_servers_degrade_gracefully(llm: FakeLLM, tools: FakeTools, service):
    tools.fail = {"search_hotels", "departures", "current_weather"}
    result = service.start("Plan 3 days in Tokyo")

    assert result["status"] == "awaiting_approval"
    assert "unavailable" in result["hotel_results"]
    assert "unavailable" in result["weather_results"]
    assert "live flight data is unavailable" in _flight_prompt(llm)


def test_flight_agent_uses_live_departures_for_the_route(llm: FakeLLM, tools: FakeTools, service):
    service.start("Plan 3 days in Tokyo from Dhaka")
    prompt = _flight_prompt(llm)

    assert "DAC (Dhaka / Hazrat Shahjalal International Airport, Dhaka) -> NRT" in prompt
    # Both Tokyo airports count; the codeshare and the Dubai flight are dropped.
    assert "BG376 Biman Bangladesh: departs 10:00, arrives 19:30 at NRT" in prompt
    assert "JL052 Japan Airlines: departs 22:40, arrives 07:55 at HND" in prompt
    assert "NH5001" not in prompt
    assert "EK585" not in prompt
    assert tools.calls.count("departures") == 1


def test_flight_agent_skips_live_lookup_without_origin(llm: FakeLLM, tools: FakeTools, service):
    llm.supervisor_reply = (
        '{"selected_agents": ["flight_agent"], '
        '"trip_constraints": {"destination": "Tokyo", "destination_iata": "NRT"}}'
    )
    service.start("Flights to Tokyo")

    assert "departures" not in tools.calls
    assert "could not be identified" in _flight_prompt(llm)


def test_flight_agent_reports_plan_restrictions(llm: FakeLLM, tools: FakeTools, service):
    restricted = '{"ok": false, "error": "function_access_restricted"}'
    tools.departures = lambda airport_iata, limit=100: restricted
    service.start("Plan 3 days in Tokyo")

    assert "live flight data is unavailable" in _flight_prompt(llm)


def test_resume_unknown_thread_is_404(service):
    with pytest.raises(AppError) as error:
        service.resume("trip_missing", approved=True)
    assert error.value.status_code == 404


def test_resume_completed_thread_is_409(service):
    thread_id = service.start("Plan 3 days in Tokyo")["thread_id"]
    service.resume(thread_id, approved=True)

    with pytest.raises(AppError) as error:
        service.resume(thread_id, approved=True)
    assert error.value.status_code == 409


def test_stream_emits_steps_then_result(service):
    events = list(service.stream_start("Plan 3 days in Tokyo"))
    nodes = [event["data"]["node"] for event in events if event["event"] == "step"]

    assert nodes[0] == "supervisor"
    assert nodes[-1] == "itinerary_agent"
    assert events[0]["data"]["selected_agents"]
    assert events[-1]["event"] == "result"
    assert events[-1]["data"]["requires_approval"] is True
