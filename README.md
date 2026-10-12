<div align="center">

# ✈️ TripMate AI

**A multi-agent travel planner powered by LangGraph, MCP (Model Context Protocol) and FastAPI.**

Turn a natural-language request into flight guidance, hotel suggestions, weather insights, a budget check and a day-by-day itinerary, reviewed by you before it is finalized.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-multi--agent-1C3C3C)
![MCP](https://img.shields.io/badge/MCP-Model%20Context%20Protocol-6E56CF)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-checkpointing-4169E1?logo=postgresql&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

</div>

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Known Limitations](#known-limitations)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

## Overview

Planning a trip usually means juggling flight trackers, hotel sites and spreadsheets. TripMate AI brings that research into a single conversational flow: describe your trip in plain language, and a pipeline of specialized agents gathers live data and assembles a structured, budget-aware travel plan.

> **Example prompt:** *"Plan a 3-day trip to Tokyo from Dhaka with a budget of $1200."*

## Features

- **Supervisor routing** — a supervisor agent reads the request, extracts trip constraints (destination, origin, duration, budget, style) and runs only the specialist agents that are needed.
- **Input guardrail** — requests unrelated to travel, or harmful, are blocked before any tool or agent runs.
- **Human-in-the-loop approval** — the graph pauses on the draft itinerary; you approve it or send feedback, and the final plan is generated accordingly.
- **MCP-based tool integration** — external services are exposed as MCP servers and consumed through `langchain-mcp-adapters`, so tools are decoupled from the agents.
- **Flight guidance** — pulls airport and airline data from the AviationStack MCP server and asks the LLM for likely airports, airlines, duration, fare range and booking advice.
- **Hotel discovery** — retrieves up-to-date accommodation suggestions through the Tavily MCP server.
- **Weather insights** — a custom MCP server (OpenWeather) provides current conditions and a forecast for the destination.
- **Budget analysis** — a budget agent assesses cost categories, risks and feasibility against the user's budget.
- **Itinerary generation** — an LLM agent combines flights, hotels, weather and budget into a practical, day-by-day draft.
- **Structured final answer** — trip summary, flights, hotels, weather, itinerary, estimated budget and recommendations.
- **Workflow visibility in the UI** — the interface shows the guardrail result, the supervisor's reasoning and the agents selected for the request.
- **PDF export** — the final travel plan can be downloaded as a PDF directly from the browser.
- **Persistent state** — each conversation is checkpointed in PostgreSQL and identified by a `thread_id`, which also lets a paused run resume later.
- **Prompt-size protection** — each section injected into a prompt is truncated to stay under the Groq per-request token limit.
- **Web interface and REST API** — a lightweight frontend served by FastAPI, plus a JSON endpoint for integrations.

## Architecture

The workflow is a LangGraph state graph with a **supervisor** that dynamically selects which specialists run. Each node reads from and writes to a shared `TravelState`. Agents never call external APIs directly: they go through an MCP client (`mcp_client.py`) that connects to three MCP servers.

```mermaid
flowchart TD
    U([User request]) --> S[Supervisor<br/>guardrail + routing]
    S -- blocked --> B[Guardrail blocked] --> E1([End])
    S -- selected agents --> F[Flight agent]
    F --> H[Hotel agent]
    H --> W[Weather agent]
    W --> BU[Budget agent]
    BU --> I[Itinerary agent<br/>draft]
    I --> HA{{Human approval<br/>interrupt}}
    HA -- approve / feedback --> R[Final agent]
    R --> E2([Final answer])

    F -. MCP stdio .-> AV[[AviationStack MCP]]
    H -. MCP HTTP .-> TV[[Tavily MCP]]
    W -. MCP stdio .-> WX[[Weather MCP<br/>custom server]]

    DB[(PostgreSQL<br/>checkpointer)] -.- HA
```

The supervisor only visits the specialists it selected (always in the order flight → hotel → weather → budget); the itinerary agent always runs.

| Step | Agent | Responsibility | Source |
|------|-------|----------------|--------|
| 1 | `supervisor` | Applies the input guardrail, picks the agents to run and extracts trip constraints | Groq (`openai/gpt-oss-120b`) |
| 2 | `flight_agent` | Reads airports and airlines, then generates flight guidance | AviationStack MCP (`uvx aviationstack-mcp`, stdio) |
| 3 | `hotel_agent` | Searches for relevant hotels at the destination | Tavily MCP (remote, streamable HTTP) |
| 4 | `weather_agent` | Extracts the destination, then fetches current weather and forecast | Weather MCP (`custom_weather_mcp_server.py`, stdio) |
| 5 | `budget_agent` | Assesses cost categories, risks and feasibility | Groq |
| 6 | `itinerary_agent` | Builds a draft itinerary from all collected results | Groq |
| 7 | `human_approval` | Pauses the graph with `interrupt()` until the user decides | LangGraph + PostgreSQL |
| 8 | `final_agent` | Produces the final answer, applying the user's feedback if any | Groq |

### Human-in-the-loop

1. `POST /api/travel` runs the graph up to the draft itinerary. At `human_approval`, `interrupt()` saves the state in PostgreSQL and the API returns `requires_approval: true` with the draft.
2. The user approves the draft, or rejects it with feedback.
3. `POST /api/travel/approve` resumes the same `thread_id` with `Command(resume={"approved": ..., "feedback": ...})`. The final agent then polishes the approved draft, or rewrites it following the feedback.

A revision is applied once; the revised plan is not submitted for a second approval.

### MCP servers

| Server | Transport | Tools used |
|--------|-----------|------------|
| Tavily | Streamable HTTP (`mcp.tavily.com`) | `tavily_search` |
| AviationStack | stdio, launched with `uvx aviationstack-mcp` | `list_airports`, `list_airlines` |
| Weather (custom, OpenWeather) | stdio, launched with the current Python interpreter | `get_current_weather`, `get_forecast` |

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI, Uvicorn |
| Orchestration | LangGraph, LangChain |
| Tool protocol | MCP via `mcp` and `langchain-mcp-adapters` |
| LLM | Groq (`openai/gpt-oss-120b`) |
| Persistence | PostgreSQL via `langgraph-checkpoint-postgres` and `psycopg` |
| External APIs | Tavily, AviationStack, OpenWeather |
| Frontend | Jinja2, HTML, CSS, JavaScript |

## Project Structure

```text
.
├── app.py                  # FastAPI application and routes
├── backend.py              # LangGraph workflow, agents and checkpointer
├── mcp_client.py           # MCP client config and tool wrappers
├── custom_weather_mcp_server.py  # Custom OpenWeather MCP server
├── requirements.txt        # Pinned Python dependencies
├── tools/                  # Legacy direct integrations (no longer used by the graph)
│   ├── fligth_tool.py      # Route parsing and AviationStack REST calls
│   └── tavily_tools.py     # Tavily search wrapper
├── templates/
│   └── index.html          # Web UI template
└── static/
    ├── script.js           # Frontend logic
    └── style.css           # Styles
```

Also at the root: `Dockerfile` (container image) and `.dockerignore` (files excluded from the build context).

## Getting Started

### Prerequisites

- Python 3.10 or newer
- A running PostgreSQL database (local or hosted)
- [`uv`](https://docs.astral.sh/uv/) installed (provides `uvx`, used to launch the AviationStack MCP server)
- API keys for [Groq](https://console.groq.com/), [Tavily](https://tavily.com/), [AviationStack](https://aviationstack.com/) and [OpenWeather](https://openweathermap.org/api)

### Installation

```bash
git clone https://github.com/<your-username>/TripeMate-AI.git
cd TripeMate-AI

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### Configuration

Create a `.env` file at the project root:

```env
DATABASE_URL=postgresql://user:password@localhost:5432/travel_db
GROQ_API_KEY=your_groq_api_key
TAVILY_API_KEY=your_tavily_api_key
AVIATIONSTACK_API_KEY=your_aviationstack_api_key
OPENWEATHER_API_KEY=your_openweather_api_key
```

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string. `sslmode=require` is appended automatically if absent. |
| `GROQ_API_KEY` | Yes | API key for the Groq LLM. The app refuses to start without it. |
| `TAVILY_API_KEY` | Yes | API key for hotel search (Tavily MCP). |
| `AVIATIONSTACK_API_KEY` | Yes | API key for airport and airline data (AviationStack MCP). |
| `OPENWEATHER_API_KEY` | Yes | API key for current weather and forecast (Weather MCP). |
| `LANGSMITH_*` | No | Optional LangSmith tracing variables. |

> ⚠️ Never commit your `.env` file. It is already listed in `.gitignore`.

### Run

```bash
python app.py
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Interactive API docs are available at [`/docs`](http://127.0.0.1:8000/docs).

On first launch, the PostgreSQL checkpoint tables are created automatically.

### Deploy on Render

The repository ships with a `Dockerfile`, so it can be deployed as a Docker web service on [Render](https://render.com/).

1. Create a **PostgreSQL** database on Render and copy its **External Database URL**.
2. Create a new **Web Service**, connect your GitHub repository and select **Docker** as the runtime.
3. In **Environment**, add the variables listed in [Configuration](#configuration) (`DATABASE_URL`, `GROQ_API_KEY`, `TAVILY_API_KEY`, `AVIATIONSTACK_API_KEY`, `OPENWEATHER_API_KEY`). Do not commit your `.env` file.
4. Deploy. The app listens on port `8000`; if Render does not detect it, set the `PORT` environment variable to `8000`.
5. Check `https://<your-service>.onrender.com/health`.

> **Tip:** if the web service and the database are in the same Render region, use the **Internal Database URL** instead; it is faster and does not leave Render's network.

### Run with Docker (local)

Build the image:

```bash
docker build -t tripmate-ai .
```

Run the container, injecting your environment variables at runtime:

```bash
docker run --rm -p 8000:8000 --env-file .env tripmate-ai
```

Then open [http://localhost:8000](http://localhost:8000).

> **Note:** inside a container, `localhost` refers to the container itself. If PostgreSQL runs on your host machine, use `host.docker.internal` in `DATABASE_URL` (Docker Desktop), or point to a hosted database.

## API Reference

### `GET /health`

Health check.

```json
{ "status": "ok", "message": "AI Travel Planner API is running" }
```

### `POST /api/travel`

Generate a travel plan.

**Request body**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message` | string | Yes | Natural-language trip request. |
| `thread_id` | string | No | Reuse a previous conversation. A new one is generated if omitted. |

```bash
curl -X POST http://127.0.0.1:8000/api/travel \
  -H "Content-Type: application/json" \
  -d '{"message": "Plan a 3-day trip to Tokyo from Dhaka with a budget of $1200"}'
```

**Response** — the run pauses on the draft itinerary:

```json
{
  "success": true,
  "thread_id": "user_3f2a…",
  "requires_approval": true,
  "approval_request": "Please review the generated draft itinerary…",
  "answer": "Draft itinerary (Markdown)",
  "itinerary": "…",
  "flight_results": "…",
  "hotel_results": "…",
  "weather_results": "…",
  "budget_results": "…",
  "selected_agents": ["flight_agent", "hotel_agent", "itinerary_agent"],
  "trip_constraints": { "destination": "Tokyo", "duration": "3 days", "budget": "$1200" },
  "supervisor_reasoning": "…",
  "guardrail_allowed": true,
  "llm_calls": 5
}
```

If the guardrail blocks the request, `guardrail_allowed` is `false`, `guardrail_reason` explains why and `answer` contains the message.

**Errors:** `400` for an empty message, `500` with `{ "success": false, "error": "…" }` on internal failures.

### `POST /api/travel/approve`

Resume a paused run after reviewing the draft.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `thread_id` | string | Yes | The `thread_id` returned by `/api/travel`. |
| `approved` | boolean | Yes | `true` to approve the draft, `false` to request a revision. |
| `feedback` | string | If `approved` is `false` | Revision instructions for the final agent. |

```bash
curl -X POST http://127.0.0.1:8000/api/travel/approve \
  -H "Content-Type: application/json" \
  -d '{"thread_id": "user_3f2a…", "approved": false, "feedback": "Add more food spots and cut the budget"}'
```

The response has the same shape as `/api/travel`, with `requires_approval: false`, `approved`, `human_feedback` and the final plan in `answer`.

**Errors:** `400` if `approved` is `false` and `feedback` is empty, `500` on internal failures.

## Known Limitations

- **No live fares.** The AviationStack MCP only exposes reference data (airports, airlines); fare ranges in the answer are LLM estimates, not real prices.
- **Sequential pipeline.** Agents run one after another, and each MCP call may start a subprocess, which adds latency.
- **Limited error handling.** Only the flight agent and the supervisor fall back gracefully; a failing hotel or weather MCP server currently fails the whole request.
- **Single revision round.** After feedback, the final plan is generated once and is not sent back for another approval.
- **LLM rate limits.** On Groq's free tier, requests are capped at 8,000 tokens per minute for `openai/gpt-oss-120b`. Prompt sections are truncated to stay under it, which can drop details from long tool results.
- **Cold start in containers.** The AviationStack MCP server is launched with `uvx`, which downloads the package on first use, so the first flight request after a deploy can be slow.

## Roadmap

- [x] MCP integration (Tavily, AviationStack, custom Weather server)
- [x] Supervisor routing and input guardrail
- [x] Budget agent
- [x] Human-in-the-loop approval
- [ ] Multiple revision rounds before finalizing
- [ ] Fare and price data (e.g. Amadeus)
- [ ] LLM-based extraction of origin, destination, dates and budget
- [ ] Parallel execution of flight, hotel and weather agents
- [ ] Graceful degradation when an MCP server is unavailable
- [ ] Streaming responses in the UI
- [x] Docker support
- [ ] CI pipeline
- [ ] Automated tests

## Contributing

Contributions are welcome.

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit your changes
4. Push the branch and open a pull request

## License

Distributed under the MIT License. See [LICENSE](LICENSE) for details.
