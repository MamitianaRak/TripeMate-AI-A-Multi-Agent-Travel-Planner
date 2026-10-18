"""Liveness and readiness probes."""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import __version__
from app.api.schemas import HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("", response_model=HealthResponse, summary="Liveness probe")
def health(request: Request) -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=__version__,
        environment=request.app.state.settings.environment,
    )


@router.get("/ready", response_model=HealthResponse, summary="Readiness probe")
def ready(request: Request):
    settings = request.app.state.settings
    service = getattr(request.app.state, "travel_service", None)
    checks: dict[str, str] = {}

    missing = settings.missing_required()
    checks["config"] = "ok" if not missing else f"missing: {', '.join(missing)}"

    if service is None:
        checks["database"] = "not initialized"
    else:
        try:
            service.check_database()
            checks["database"] = "ok"
        except Exception as exc:
            logger.warning("Readiness database check failed: %s", exc)
            checks["database"] = "error"

    healthy = all(value == "ok" for value in checks.values())
    body = HealthResponse(
        status="ok" if healthy else "degraded",
        version=__version__,
        environment=settings.environment,
        checks=checks,
    )
    return JSONResponse(status_code=200 if healthy else 503, content=body.model_dump())
