"""Helpers that turn raw tool output into compact text.

They only shape raw API data (search snippets, weather payloads). LLM answers
are never trimmed: oversized prompts are condensed by the LLM instead
(see `TravelAgents._fit`).
"""

import json
from typing import Any


def clip(value: Any, max_chars: int) -> str:
    """Shorten raw API text to whole sentences (or lines) within max_chars."""
    text = str(value or "").strip()

    if len(text) <= max_chars:
        return text

    window = text[:max_chars]
    end = max(
        window.rfind(". "),
        window.rfind("! "),
        window.rfind("? "),
        window.rfind("\n"),
    )

    if end >= max_chars * 0.5:
        return window[: end + 1].rstrip()

    return window.rsplit(" ", 1)[0].rstrip()


def tool_text(result: Any) -> str:
    """Flatten an MCP tool result (str, dict or list of content blocks) into text."""
    if isinstance(result, str):
        return result

    if isinstance(result, list):
        parts = [
            str(block.get("text", "")) if isinstance(block, dict) else str(block)
            for block in result
        ]
        return "\n".join(part for part in parts if part)

    if isinstance(result, dict):
        return json.dumps(result, ensure_ascii=False)

    return str(result)


def short_sentences(text: Any, max_chars: int) -> str:
    """Collapse whitespace and keep whole sentences within max_chars."""
    return clip(" ".join(str(text or "").split()), max_chars)


def compact_hotels(result: Any, max_results: int = 5, snippet_chars: int = 250) -> str:
    """Turn the raw Tavily payload into a short list: name, link, one-line summary."""
    text = tool_text(result)

    try:
        data = json.loads(text)
    except ValueError:
        return short_sentences(text, 2500)

    items = data.get("results") if isinstance(data, dict) else data

    if not isinstance(items, list):
        return short_sentences(text, 2500)

    lines = []
    for index, item in enumerate(items[:max_results], 1):
        if not isinstance(item, dict):
            continue

        title = item.get("title") or "Unknown"
        url = item.get("url") or ""
        summary = short_sentences(item.get("content", ""), snippet_chars)
        lines.append(f"{index}. {title} - {url}\n   {summary}")

    return "\n".join(lines) or short_sentences(text, 2500)


def _time(value: Any) -> str:
    """'2026-10-18T05:20:00.000' -> '05:20'."""
    text = str(value or "")
    return text[11:16] if len(text) >= 16 else "?"


def route_departures(result: Any, arrival_codes: set[str], max_flights: int = 8) -> str:
    """Keep only today's departures that land at the destination, one line each.

    Raises RuntimeError when the MCP server reports an error (for example a
    feature that the AviationStack plan does not include).
    """
    payload = json.loads(tool_text(result))

    if not payload.get("ok", False):
        raise RuntimeError(payload.get("error") or "AviationStack returned an error.")

    lines: list[str] = []
    seen: set[tuple[str, str]] = set()

    for flight in payload.get("data", []):
        if flight.get("arrival_airport_code") not in arrival_codes:
            continue

        departure = _time(flight.get("departure_scheduled_time"))
        arrival = _time(flight.get("arrival_scheduled_time"))

        # Codeshares repeat the same physical flight under other flight numbers.
        if (departure, arrival) in seen:
            continue
        seen.add((departure, arrival))

        lines.append(
            f"- {flight.get('flight_number') or '?'} {flight.get('airline') or 'Unknown airline'}: "
            f"departs {departure}, arrives {arrival} at {flight.get('arrival_airport_code')}"
        )

        if len(lines) >= max_flights:
            break

    return "\n".join(lines)


def json_from_llm(text: str) -> dict[str, Any]:
    """Extract the first complete JSON object returned by the model."""
    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end < start:
        raise ValueError("The model did not return a JSON object.")

    return json.loads(text[start : end + 1])
