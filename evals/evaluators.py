"""Code evaluators for one TripMate run. Deterministic and free: no LLM judge, so a score can be
trusted and re-run. Each check returns None when the case does not ask for it."""

import re
import unicodedata

from app.agents.state import AGENT_ORDER, SPECIALIST_AGENTS

# Which tools each specialist may call: a call outside this map is an agent that should not run.
AGENT_TOOLS = {
    "flight_agent": {"departures"},
    "hotel_agent": {"search_hotels"},
    "weather_agent": {"current_weather", "forecast"},
    "budget_agent": set(),
}

CHECKS = (
    "guardrail_ok",
    "required_ok",
    "unwanted_ok",
    "path_ok",
    "tools_ok",
    "constraints_ok",
    "paused_ok",
    "resume_ok",
)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text).lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def expected_path(selected: list[str], allowed: bool, resumed: bool) -> list[str]:
    """The node sequence the graph must follow for this supervisor decision."""
    if not allowed:
        return ["supervisor", "guardrail_blocked"]
    specialists = [a for a in AGENT_ORDER if a in selected and a in SPECIALIST_AGENTS]
    path = ["supervisor", *specialists, "itinerary_agent", "__interrupt__"]
    return [*path, "human_approval", "final_agent"] if resumed else path


def _iata_ok(expected: list[str] | None, actual: str) -> bool | None:
    return None if not expected else str(actual or "").strip().upper() in expected


def score(case: dict, run: dict) -> dict:
    """One case and what the graph did -> its checks (True/False, or None when not asked)."""
    expect = case["expect"]
    allowed = run.get("allowed")
    selected = [a for a in run.get("selected_agents", []) if a in SPECIALIST_AGENTS]
    resumed = "resume" in case and allowed is True
    out: dict = {"selected": selected}

    out["guardrail_ok"] = allowed == expect["allowed"]
    graded = expect["allowed"] and allowed
    required, unwanted = set(expect.get("required", [])), set(expect.get("unwanted", []))
    out["required_ok"] = None if not graded or not required else required <= set(selected)
    out["unwanted_ok"] = None if not graded or not unwanted else not unwanted & set(selected)
    out["missing_agents"] = sorted(required - set(selected)) if graded else []
    out["extra_agents"] = sorted(unwanted & set(selected)) if graded else []

    # Trajectory: the nodes actually executed, in order, against the path the decision implies.
    out["path_ok"] = run.get("path") == expected_path(selected, bool(allowed), resumed)

    # Tools: every call must belong to a selected agent; a blocked request calls none.
    allowed_tools = set().union(*(AGENT_TOOLS[a] for a in selected)) if selected else set()
    stray = sorted({t for t in run.get("tool_calls", []) if t not in allowed_tools})
    out["stray_tools"] = stray
    out["tools_ok"] = not stray

    constraints = run.get("trip_constraints") or {}
    checks = [
        _iata_ok(expect.get("origin_iata"), constraints.get("origin_iata")),
        _iata_ok(expect.get("destination_iata"), constraints.get("destination_iata")),
    ]
    if expect.get("budget"):
        budget = re.sub(r"[\s,.]", "", str(constraints.get("budget", "")))
        checks.append(any(b in budget for b in expect["budget"]))
    asked = [c for c in checks if c is not None]
    out["constraints_ok"] = None if not graded or not asked else all(asked)

    # Human-in-the-loop: an allowed request must stop for approval before any final answer.
    out["paused_ok"] = None if not graded else run.get("paused_for_approval") is True
    if not resumed:
        out["resume_ok"] = None
    else:
        final = normalize(run.get("final_response", ""))
        mentions = expect.get("final_mentions") or []
        out["resume_ok"] = (
            bool(final)
            and run.get("approved") == case["resume"]["approved"]
            and all(any(normalize(m) in final for m in group) for group in mentions)
        )

    checks_run = [out[k] for k in CHECKS if out[k] is not None]
    out["passed"] = all(checks_run)
    return out


def summarize(rows: list[dict]) -> dict:
    def mean(values: list) -> tuple:
        return (round(sum(values) / len(values), 3), len(values)) if values else (None, 0)

    summary = {
        k: mean([r["score"][k] for r in rows if r["score"].get(k) is not None]) for k in CHECKS
    }
    summary["passed"] = mean([r["score"]["passed"] for r in rows])
    return summary
