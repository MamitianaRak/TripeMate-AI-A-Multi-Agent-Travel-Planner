"""LLM factory."""

from langchain_groq import ChatGroq

from app.core.config import Settings


def build_llm(settings: Settings) -> ChatGroq:
    options = {}
    if settings.llm_reasoning_effort:
        options["reasoning_effort"] = settings.llm_reasoning_effort

    return ChatGroq(
        model=settings.groq_model,
        api_key=settings.groq_api_key,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        **options,
    )
