"""Trajectory evaluation of the multi-agent graph with the real LLM.

    python -m evals.run                         # every case, stub tools
    python -m evals.run --category guardrail    # one category
    python -m evals.run --case hitl-revise      # one case, repeatable
    python -m evals.run --live-tools            # real MCP servers (spends API quotas)
    python -m evals.run --min-pass 0.9          # exit 1 below that pass rate (regression gate)

Each case runs on a fresh thread with an in-memory checkpointer. The run records the nodes the
graph executed, the tools the agents called, the LLM calls and tokens, then scores the path.
Results go to evals/results/: a JSON file per run (not versioned) and latest.md for a full run.
"""

import argparse
import json
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_core.callbacks import BaseCallbackHandler
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from app.agents.graph import build_travel_graph
from app.agents.state import initial_state
from app.core.config import Settings
from app.core.llm import build_llm
from evals.evaluators import score, summarize
from evals.tools import RecordingTools, StubTools

DATASET = Path(__file__).with_name("dataset.json")
RESULTS = Path(__file__).with_name("results")
LABELS = {
    "guardrail_ok": "Guardrail decision (allowed or blocked)",
    "required_ok": "Needed specialists selected",
    "unwanted_ok": "Unneeded specialists left out",
    "path_ok": "Node sequence matches the plan",
    "tools_ok": "No tool called by an unselected agent",
    "constraints_ok": "Airports and budget extracted",
    "paused_ok": "Stopped for human approval",
    "resume_ok": "Final answer follows the approval or feedback",
    "passed": "Cases passing every check",
}


class UsageCounter(BaseCallbackHandler):
    """Counts LLM calls and tokens of one case."""

    def __init__(self) -> None:
        self.calls = self.input_tokens = self.output_tokens = 0

    def on_chat_model_start(self, *args: Any, **kwargs: Any) -> None:
        self.calls += 1

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        for generations in response.generations:
            for generation in generations:
                usage = getattr(getattr(generation, "message", None), "usage_metadata", None) or {}
                self.input_tokens += usage.get("input_tokens", 0)
                self.output_tokens += usage.get("output_tokens", 0)


def run_graph(graph, graph_input: Any, config: dict, path: list[str]) -> bool:
    """Stream one leg of the run, append executed nodes to `path`; True if it paused."""
    paused = False
    for update in graph.stream(graph_input, config=config, stream_mode="updates"):
        for node in update:
            path.append(node)
            paused = paused or node == "__interrupt__"
    return paused


def run_case(graph, tools: RecordingTools, case: dict, run_id: str) -> dict:
    tools.calls.clear()
    usage = UsageCounter()
    config = {
        "configurable": {"thread_id": f"eval-{run_id}-{case['id']}"},
        "callbacks": [usage],
        "tags": ["eval", run_id],
        "metadata": {"eval_run": run_id, "eval_case": case["id"], "category": case["category"]},
    }
    path: list[str] = []
    started = time.perf_counter()
    try:
        paused = run_graph(graph, initial_state(case["question"]), config, path)
        if paused and "resume" in case:
            run_graph(graph, Command(resume=case["resume"]), config, path)
        state = graph.get_state(config).values
        error = None
    except Exception as exc:  # a provider outage or quota is recorded, not hidden
        paused, state, error = False, {}, f"{type(exc).__name__}: {exc}"

    run = {
        "id": case["id"],
        "category": case["category"],
        "question": case["question"],
        "seconds": round(time.perf_counter() - started, 1),
        "error": error,
        "allowed": state.get("guardrail_allowed"),
        "selected_agents": state.get("selected_agents", []),
        "trip_constraints": state.get("trip_constraints", {}),
        "path": path,
        "tool_calls": list(tools.calls),
        "paused_for_approval": paused,
        "approved": state.get("approved"),
        "final_response": state.get("final_response", ""),
        "llm_calls": usage.calls,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
    }
    run["score"] = score(case, run)
    return run


def percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0%}"


def markdown(run: dict) -> str:
    summary, rows = run["summary"], run["rows"]
    lines = [
        f"# Trajectory evaluation {run['run_id']}",
        "",
        f"{run['started']} · {len(rows)} cases · dataset v{run['dataset_version']} · "
        f"model {run['model']} · tools: {run['tools']}",
        "",
        "| Check | Score | Cases |",
        "|---|---|---|",
    ]
    for key, label in LABELS.items():
        value, count = summary[key]
        lines.append(f"| {label} | {percent(value)} | {count} |")

    seconds = sorted(r["seconds"] for r in rows)
    n = len(rows)
    lines += [
        "",
        f"Latency per request (until the approval pause, or the end): median "
        f"{seconds[n // 2]} s, max {seconds[-1]} s. LLM calls per request: "
        f"{sum(r['llm_calls'] for r in rows) / n:.1f} on average. Tokens per request: "
        f"{sum(r['input_tokens'] for r in rows) // n} in, "
        f"{sum(r['output_tokens'] for r in rows) // n} out on average.",
        "",
        "| Case | Category | Agents selected | Path | LLM calls | Result | Note |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        s = r["score"]
        notes = [r["error"]] if r["error"] else []
        notes += ["wrong guardrail decision"] if not s["guardrail_ok"] else []
        notes += [f"missing: {', '.join(s['missing_agents'])}"] if s["missing_agents"] else []
        notes += [f"unneeded: {', '.join(s['extra_agents'])}"] if s["extra_agents"] else []
        notes += [f"stray tools: {', '.join(s['stray_tools'])}"] if s["stray_tools"] else []
        notes += ["constraints"] if s["constraints_ok"] is False else []
        notes += ["no approval pause"] if s["paused_ok"] is False else []
        notes += ["final answer"] if s["resume_ok"] is False else []
        agents = ", ".join(a.removesuffix("_agent") for a in s["selected"]) or "none"
        path = " → ".join(p.removesuffix("_agent") for p in r["path"])
        lines.append(
            f"| {r['id']} | {r['category']} | {agents} | {path} | {r['llm_calls']} | "
            f"{'pass' if s['passed'] else 'FAIL'} | {'; '.join(notes)} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--category", help="run one category only")
    parser.add_argument("--case", action="append", help="case id, repeatable")
    parser.add_argument("--live-tools", action="store_true", help="real MCP servers")
    parser.add_argument("--delay", type=float, default=3.0, help="seconds between cases")
    parser.add_argument("--min-pass", type=float, help="exit 1 below this pass rate")
    args = parser.parse_args()

    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    cases = [
        c
        for c in dataset["cases"]
        if (not args.category or c["category"] == args.category)
        and (not args.case or c["id"] in args.case)
    ]
    if not cases:
        print("No case matches.")
        return 1

    load_dotenv()  # LangSmith reads LANGSMITH_* from the process environment
    settings = Settings()
    toolbox = None
    if args.live_tools:
        from app.integrations.mcp_toolbox import McpToolbox, build_mcp_client

        toolbox = McpToolbox(build_mcp_client(settings), timeout=settings.mcp_timeout_seconds)
    tools = RecordingTools(toolbox or StubTools())
    graph = build_travel_graph(
        llm=build_llm(settings),
        tools=tools,
        checkpointer=MemorySaver(),
        prompt_budget_tokens=settings.prompt_budget_tokens,
        max_continuations=settings.llm_max_continuations,
    )

    run_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
    rows = []
    try:
        for i, case in enumerate(cases, 1):
            row = run_case(graph, tools, case, run_id)
            rows.append(row)
            print(
                f"[{i}/{len(cases)}] {'pass' if row['score']['passed'] else 'FAIL':4} "
                f"{case['id']:26} {row['seconds']:>5} s  "
                f"{', '.join(row['score']['selected']) or '-'}"
                + (f"  {row['error'][:90]}" if row["error"] else ""),
                flush=True,
            )
            if i < len(cases):
                time.sleep(args.delay)
    finally:
        if toolbox is not None:
            toolbox.close()

    run = {
        "run_id": run_id,
        "started": run_id[:15],
        "dataset_version": dataset["version"],
        "model": settings.groq_model,
        "tools": "live MCP servers" if args.live_tools else "stubs",
        "summary": summarize(rows),
        "rows": rows,
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"{run_id}.json").write_text(
        json.dumps(run, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    report = markdown(run)
    if not args.category and not args.case:
        (RESULTS / "latest.md").write_text(report, encoding="utf-8")
    print("\n" + report)

    pass_rate = run["summary"]["passed"][0] or 0
    if args.min_pass is not None and pass_rate < args.min_pass:
        print(f"Pass rate {pass_rate:.0%} is below the required {args.min_pass:.0%}.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
