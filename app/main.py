"""FastAPI application factory."""

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

import certifi
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import health, travel
from app.api.errors import register_error_handlers
from app.core.config import Settings, get_settings
from app.core.logging import request_id_var, setup_logging
from app.core.rate_limit import RateLimiter
from app.services.travel_service import TravelService

logger = logging.getLogger(__name__)

# Some Windows/Python installs miss root certificates for the external APIs.
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())


def build_production_service(settings: Settings):
    """Wire the real LLM, MCP servers and PostgreSQL checkpointer.

    Returns the service and a cleanup callback.
    """
    from dotenv import load_dotenv
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    from app.agents.graph import build_travel_graph
    from app.core.llm import build_llm
    from app.integrations.mcp_toolbox import McpToolbox, build_mcp_client

    # Settings read .env directly, but LangChain reads LANGSMITH_* from the
    # process environment, so export .env there too (real env vars win).
    load_dotenv(override=False)

    missing = settings.missing_required()
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    # A pool (instead of one shared connection) lets concurrent requests
    # read and write checkpoints without blocking each other.
    pool = ConnectionPool(
        conninfo=settings.database_conninfo,
        max_size=settings.database_pool_size,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=True,
    )
    checkpointer = PostgresSaver(pool)
    checkpointer.setup()

    toolbox = McpToolbox(build_mcp_client(settings), timeout=settings.mcp_timeout_seconds)
    graph = build_travel_graph(
        llm=build_llm(settings),
        tools=toolbox,
        checkpointer=checkpointer,
        prompt_budget_tokens=settings.prompt_budget_tokens,
        max_continuations=settings.llm_max_continuations,
    )

    def cleanup() -> None:
        toolbox.close()
        pool.close()

    return TravelService(graph), cleanup


def create_app(
    settings: Settings | None = None,
    travel_service: TravelService | None = None,
) -> FastAPI:
    """Build the app. Passing `travel_service` skips production wiring (tests)."""
    settings = settings or get_settings()
    setup_logging(settings.log_level, settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        cleanup = None

        if app.state.travel_service is None:
            app.state.travel_service, cleanup = build_production_service(settings)

        logger.info("TripMate AI %s started (%s)", __version__, settings.environment)
        yield

        if cleanup:
            cleanup()

    app = FastAPI(
        title="TripMate AI",
        description="Multi-agent travel planner built with LangGraph, MCP and FastAPI.",
        version=__version__,
        lifespan=lifespan,
    )

    app.state.settings = settings
    app.state.travel_service = travel_service
    app.state.rate_limiter = RateLimiter(
        settings.rate_limit_requests, settings.rate_limit_window_seconds
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        token = request_id_var.set(request_id)
        started = time.perf_counter()

        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "%s %s -> %s in %.0f ms",
                request.method,
                request.url.path,
                response.status_code,
                (time.perf_counter() - started) * 1000,
            )
            return response
        finally:
            request_id_var.reset(token)

    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(travel.router)

    return app


app = create_app()
