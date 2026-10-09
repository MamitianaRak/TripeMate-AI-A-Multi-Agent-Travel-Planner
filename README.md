<div align="center">

# ✈️ TripMate AI

**A multi-agent travel planner powered by LangGraph, LangChain and FastAPI.**

Turn a natural-language request into flight information, hotel suggestions and a day-by-day itinerary.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-multi--agent-1C3C3C)
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

- **Flight research** — resolves origin and destination (country, city or IATA code) and fetches live flight data from AviationStack.
- **Hotel discovery** — retrieves up-to-date accommodation suggestions through Tavily web search.
- **Itinerary generation** — an LLM agent combines flights and hotels into a practical, day-by-day plan.
- **Structured final answer** — trip summary, flights, hotels, itinerary, estimated budget and recommendations.
- **Persistent state** — each conversation is checkpointed in PostgreSQL and identified by a `thread_id`.
- **Web interface and REST API** — a lightweight frontend served by FastAPI, plus a JSON endpoint for integrations.

## Architecture

The workflow is a linear LangGraph state graph. Each node reads from and writes to a shared `TravelState`.

```mermaid
flowchart LR
    U([User request]) --> F[Flight agent<br/>AviationStack]
    F --> H[Hotel agent<br/>Tavily]
    H --> I[Itinerary agent<br/>Groq LLM]
    I --> R[Final agent<br/>Groq LLM]
    R --> A([Formatted answer])
    DB[(PostgreSQL<br/>checkpointer)] -.-> F
    DB -.-> H
    DB -.-> I
    DB -.-> R
```

| Step | Agent | Responsibility | Data source |
|------|-------|----------------|-------------|
| 1 | `flight_agent` | Parses the route from the query and fetches live flights | AviationStack |
| 2 | `hotel_agent` | Searches for relevant hotels at the destination | Tavily |
| 3 | `itinerary_agent` | Builds a practical, budget-aware itinerary | Groq (`openai/gpt-oss-120b`) |
| 4 | `final_agent` | Formats the complete response into clear sections | Groq (`openai/gpt-oss-120b`) |

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI, Uvicorn |
| Orchestration | LangGraph, LangChain |
| LLM | Groq (`openai/gpt-oss-120b`) |
| Persistence | PostgreSQL via `langgraph-checkpoint-postgres` and `psycopg` |
| External APIs | Tavily, AviationStack |
| Frontend | Jinja2, HTML, CSS, JavaScript |

## Project Structure

```text
.
├── app.py                  # FastAPI application and routes
├── backend.py              # LangGraph workflow, agents and checkpointer
├── requirements.txt        # Pinned Python dependencies
├── tools/
│   ├── fligth_tool.py      # Route parsing and AviationStack integration
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
- API keys for [Groq](https://console.groq.com/), [Tavily](https://tavily.com/) and [AviationStack](https://aviationstack.com/)

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
DEFAULT_ORIGIN_IATA=FRA
```

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string. `sslmode=require` is appended automatically if absent. |
| `GROQ_API_KEY` | Yes | API key for the Groq LLM. The app refuses to start without it. |
| `TAVILY_API_KEY` | Yes | API key for hotel web search. |
| `AVIATIONSTACK_API_KEY` | Yes | API key for flight data. |
| `DEFAULT_ORIGIN_IATA` | No | Departure airport used when the query mentions only a destination. Defaults to `FRA`. |

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
3. In **Environment**, add the variables listed in [Configuration](#configuration) (`DATABASE_URL`, `GROQ_API_KEY`, `TAVILY_API_KEY`, `AVIATIONSTACK_API_KEY`, optionally `DEFAULT_ORIGIN_IATA`). Do not commit your `.env` file.
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

- **No ticket prices.** AviationStack returns live flight status and schedules, not fares. The final answer states this explicitly.
- **Heuristic route parsing.** Origin and destination are extracted with regular expressions and a built-in city/country lookup, so unusual phrasing may fall back to the default origin.
- **Sequential pipeline.** Agents run one after another; there is no retry or fallback if an external API fails.
- **AviationStack free tier** is served over HTTP and has limited monthly requests.

## Roadmap

- [ ] Fare and price data (e.g. Amadeus)
- [ ] LLM-based extraction of origin, destination, dates and budget
- [ ] Parallel execution of flight and hotel agents
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
