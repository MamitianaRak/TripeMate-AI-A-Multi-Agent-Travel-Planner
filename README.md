<div align="center">

# ✈️ TripMate AI

**A multi-agent travel planner powered by LangGraph, MCP (Model Context Protocol) and FastAPI.**

Turn a natural-language request into flight guidance, hotel suggestions, weather insights and a day-by-day itinerary.

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

- **MCP-based tool integration** — external services are exposed as MCP servers and consumed through `langchain-mcp-adapters`, so tools are decoupled from the agents.
- **Flight guidance** — pulls airport and airline data from the AviationStack MCP server and asks the LLM for likely airports, airlines, duration, fare range and booking advice.
- **Hotel discovery** — retrieves up-to-date accommodation suggestions through the Tavily MCP server.
- **Weather insights** — a custom MCP server (OpenWeather) provides current conditions and a forecast for the destination.
- **Itinerary generation** — an LLM agent combines flights, hotels and weather into a practical, day-by-day plan.
- **Structured final answer** — trip summary, flights, hotels, weather, itinerary, estimated budget and recommendations.
- **Persistent state** — each conversation is checkpointed in PostgreSQL and identified by a `thread_id`.
- **Web interface and REST API** — a lightweight frontend served by FastAPI, plus a JSON endpoint for integrations.

## Architecture

The workflow is a linear LangGraph state graph. Each node reads from and writes to a shared `TravelState`. Agents never call external APIs directly: they go through an MCP client (`mcp_client.py`) that connects to three MCP servers.

```mermaid
flowchart LR
    U([User request]) --> F[Flight agent]
    F --> H[Hotel agent]
    H --> W[Weather agent]
    W --> I[Itinerary agent]
    I --> R[Final agent]
    R --> A([Formatted answer])

    F -. MCP stdio .-> AV[[AviationStack MCP]]
    H -. MCP HTTP .-> TV[[Tavily MCP]]
    W -. MCP stdio .-> WX[[Weather MCP<br/>custom server]]
    I --> LLM{{Groq LLM}}
    R --> LLM
    F --> LLM

    DB[(PostgreSQL<br/>checkpointer)] -.- F
```

| Step | Agent | Responsibility | MCP server / source |
|------|-------|----------------|---------------------|
| 1 | `flight_agent` | Reads airports and airlines, then generates flight guidance with the LLM | AviationStack MCP (`uvx aviationstack-mcp`, stdio) |
| 2 | `hotel_agent` | Searches for relevant hotels at the destination | Tavily MCP (remote, streamable HTTP) |
| 3 | `weather_agent` | Extracts the destination with the LLM, then fetches current weather and forecast | Weather MCP (`custom_weather_mcp_server.py`, stdio) |
| 4 | `itinerary_agent` | Builds a practical, budget-aware itinerary | Groq (`openai/gpt-oss-120b`) |
| 5 | `final_agent` | Formats the complete response into clear sections | Groq (`openai/gpt-oss-120b`) |

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

**Response**

```json
{
  "success": true,
  "thread_id": "user_3f2a…",
  "answer": "Formatted final travel plan (Markdown)",
  "flight_results": "…",
  "hotel_results": "…",
  "itinerary": "…",
  "llm_calls": 4
}
```

**Errors:** `400` for an empty message, `500` with `{ "success": false, "error": "…" }` on internal failures.

## Known Limitations

- **No live fares.** The AviationStack MCP only exposes reference data (airports, airlines); fare ranges in the answer are LLM estimates, not real prices.
- **Sequential pipeline.** Agents run one after another, and each MCP call may start a subprocess, which adds latency.
- **Limited error handling.** Only the flight agent falls back gracefully; a failing hotel or weather MCP server currently fails the whole request.
- **Cold start in containers.** The AviationStack MCP server is launched with `uvx`, which downloads the package on first use, so the first flight request after a deploy can be slow.

## Roadmap

- [x] MCP integration (Tavily, AviationStack, custom Weather server)
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
