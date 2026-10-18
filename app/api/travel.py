"""Travel-planning endpoints (JSON and Server-Sent Events)."""

import contextvars
import json
import queue
import threading
from collections.abc import Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.deps import get_travel_service, rate_limit
from app.api.errors import error_body, to_app_error
from app.api.schemas import ApprovalRequest, ErrorResponse, TravelRequest, TravelResponse
from app.services.travel_service import StepEvent, TravelService

router = APIRouter(prefix="/api/travel", tags=["travel"])

ERROR_RESPONSES = {
    400: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    429: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
    504: {"model": ErrorResponse},
}


_DONE = object()


def _in_worker_thread(events: Iterator[StepEvent]) -> Iterator[StepEvent]:
    """Drive the whole graph stream from one dedicated thread.

    The response iterator may be resumed on different threadpool threads, which
    breaks LangGraph's context variables; a single worker thread avoids that.
    """
    channel: queue.Queue = queue.Queue()
    context = contextvars.copy_context()

    def worker() -> None:
        try:
            for item in events:
                channel.put(item)
        except Exception as exc:
            channel.put(exc)
        finally:
            channel.put(_DONE)

    threading.Thread(target=context.run, args=(worker,), daemon=True).start()

    while (item := channel.get()) is not _DONE:
        if isinstance(item, Exception):
            raise item
        yield item


def _format_sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _sse(events: Iterator[StepEvent]) -> Iterator[str]:
    """Format events as SSE; failures mid-stream become an `error` event."""
    try:
        for item in _in_worker_thread(events):
            yield _format_sse(item["event"], item["data"])
    except Exception as exc:
        error = to_app_error(exc)
        yield _format_sse("error", error_body(error.code, error.message))


def _stream_response(events: Iterator[StepEvent]) -> StreamingResponse:
    return StreamingResponse(
        _sse(events),
        media_type="text/event-stream",
        # Disable proxy buffering so steps reach the browser as they happen.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# Endpoints are sync on purpose: FastAPI runs them in a worker thread, so the
# blocking graph and the MCP calls never block the event loop.
@router.post(
    "",
    response_model=TravelResponse,
    responses=ERROR_RESPONSES,
    dependencies=[Depends(rate_limit)],
    summary="Start a travel plan and pause on the draft itinerary",
)
def start_plan(body: TravelRequest, service: TravelService = Depends(get_travel_service)):
    return service.start(body.message, body.thread_id)


@router.post(
    "/approve",
    response_model=TravelResponse,
    responses=ERROR_RESPONSES,
    dependencies=[Depends(rate_limit)],
    summary="Approve or revise the draft and generate the final plan",
)
def approve_plan(body: ApprovalRequest, service: TravelService = Depends(get_travel_service)):
    return service.resume(body.thread_id, body.approved, body.feedback)


@router.post(
    "/stream",
    responses=ERROR_RESPONSES,
    dependencies=[Depends(rate_limit)],
    summary="Start a travel plan, streaming one event per agent step",
)
def stream_plan(body: TravelRequest, service: TravelService = Depends(get_travel_service)):
    return _stream_response(service.stream_start(body.message, body.thread_id))


@router.post(
    "/approve/stream",
    responses=ERROR_RESPONSES,
    dependencies=[Depends(rate_limit)],
    summary="Resume a paused plan, streaming one event per agent step",
)
def stream_approval(body: ApprovalRequest, service: TravelService = Depends(get_travel_service)):
    return _stream_response(service.stream_resume(body.thread_id, body.approved, body.feedback))
