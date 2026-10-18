"""FastAPI dependencies."""

import math

from fastapi import Request

from app.core.errors import AppError
from app.services.travel_service import TravelService


def get_travel_service(request: Request) -> TravelService:
    service = getattr(request.app.state, "travel_service", None)

    if service is None:
        raise AppError(503, "service_unavailable", "The travel planner is not ready yet.")

    return service


def client_ip(request: Request) -> str:
    if request.app.state.settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()

    return request.client.host if request.client else "unknown"


def rate_limit(request: Request) -> None:
    retry_after = request.app.state.rate_limiter.check(client_ip(request))

    if retry_after is not None:
        seconds = max(math.ceil(retry_after), 1)
        raise AppError(
            429,
            "rate_limited",
            f"Too many requests. Please retry in {seconds} seconds.",
            headers={"Retry-After": str(seconds)},
        )
