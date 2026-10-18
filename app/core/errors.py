"""Application errors and their mapping to HTTP responses."""

from dataclasses import dataclass, field


@dataclass(eq=False)
class AppError(Exception):
    status_code: int
    code: str
    message: str
    headers: dict[str, str] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message


def classify_provider_error(exc: Exception) -> AppError | None:
    """Map upstream LLM/network failures to actionable client errors.

    Matching on class names keeps this module free of provider SDK imports.
    """
    if isinstance(exc, AppError):
        return exc

    name = type(exc).__name__
    text = str(exc).lower()

    if name == "RateLimitError" or "rate_limit_exceeded" in text or "request too large" in text:
        return AppError(
            503,
            "llm_rate_limited",
            "The AI provider is rate-limiting requests. Please wait a minute and try again.",
        )

    if "Timeout" in name or isinstance(exc, TimeoutError):
        return AppError(
            504,
            "upstream_timeout",
            "An external service took too long to respond. Please try again.",
        )

    if name in {"APIConnectionError", "ConnectError", "ConnectionError"}:
        return AppError(
            503,
            "upstream_unavailable",
            "An external service is unreachable right now. Please try again later.",
        )

    return None
