"""The trajectory evaluation's own checks, on the real graph with the fake LLM."""

import json
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver

from app.agents.graph import build_travel_graph
from evals.evaluators import expected_path, score
from evals.run import run_case
from evals.tools import RecordingTools
from tests.fakes import FakeLLM, FakeTools

DATASET = json.loads(
    (Path(__file__).resolve().parents[1] / "evals" / "dataset.json").read_text("utf-8")
)


def _run(llm: FakeLLM, case: dict) -> dict:
    tools = RecordingTools(FakeTools())
    graph = build_travel_graph(llm=llm, tools=tools, checkpointer=MemorySaver())
    return run_case(graph, tools, case, "test")


def test_a_full_trip_pauses_for_approval_after_the_selected_specialists():
    case = {
        "id": "t",
        "category": "routing",
        "question": "Plan 3 days in Tokyo from Dhaka",
        "expect": {
            "allowed": True,
            "required": ["flight_agent"],
            "unwanted": [],
            "origin_iata": ["DAC"],
            "destination_iata": ["NRT", "HND"],
        },
    }
    run = _run(FakeLLM(), case)

    assert run["path"] == [
        "supervisor",
        "flight_agent",
        "hotel_agent",
        "weather_agent",
        "budget_agent",
        "itinerary_agent",
        "__interrupt__",
    ]
    assert run["paused_for_approval"] is True
    assert set(run["tool_calls"]) == {"departures", "search_hotels", "current_weather", "forecast"}
    assert run["llm_calls"] >= 3
    assert run["score"]["passed"] is True


def test_an_unneeded_agent_fails_the_case():
    case = {
        "id": "t",
        "category": "routing",
        "question": "Weather in Tokyo?",
        "expect": {"allowed": True, "required": ["weather_agent"], "unwanted": ["flight_agent"]},
    }
    run = _run(FakeLLM(selected_agents=["flight_agent", "weather_agent"]), case)

    assert run["score"]["unwanted_ok"] is False
    assert run["score"]["extra_agents"] == ["flight_agent"]
    assert run["score"]["passed"] is False


def test_a_blocked_request_runs_no_specialist_and_no_tool():
    case = {
        "id": "t",
        "category": "guardrail",
        "question": "Explain photosynthesis",
        "expect": {"allowed": False},
    }
    run = _run(FakeLLM(allowed=False), case)

    assert run["path"] == ["supervisor", "guardrail_blocked"]
    assert run["tool_calls"] == []
    assert run["score"]["passed"] is True


def test_resume_with_feedback_reaches_the_final_agent():
    case = {
        "id": "t",
        "category": "human-in-the-loop",
        "question": "Plan 3 days in Tokyo",
        "resume": {"approved": False, "feedback": "Add a day in Nikko"},
        "expect": {
            "allowed": True,
            "required": [],
            "unwanted": [],
            "final_mentions": [["revised"]],
        },
    }
    run = _run(FakeLLM(selected_agents=[]), case)

    assert run["path"][-3:] == ["__interrupt__", "human_approval", "final_agent"]
    assert run["approved"] is False
    assert run["score"]["resume_ok"] is True


def test_stray_tool_calls_are_flagged():
    case = {"expect": {"allowed": True, "required": [], "unwanted": []}}
    run = {
        "allowed": True,
        "selected_agents": ["hotel_agent"],
        "tool_calls": ["departures"],
        "path": expected_path(["hotel_agent"], True, False),
        "paused_for_approval": True,
    }
    assert score(case, run)["stray_tools"] == ["departures"]


def test_dataset_is_well_formed():
    ids = [c["id"] for c in DATASET["cases"]]
    assert len(ids) == len(set(ids)), "duplicate case id"
    agents = {"flight_agent", "hotel_agent", "weather_agent", "budget_agent"}
    for case in DATASET["cases"]:
        expect = case["expect"]
        assert set(expect.get("required", [])) <= agents, case["id"]
        assert set(expect.get("unwanted", [])) <= agents, case["id"]
        assert not set(expect.get("required", [])) & set(expect.get("unwanted", [])), case["id"]
        if "resume" in case:
            assert expect["allowed"] is True, case["id"]
