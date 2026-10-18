"""Offline airport lookup (airportsdata): validates IATA codes without API quota."""

from functools import lru_cache

import airportsdata


@lru_cache(maxsize=1)
def _airports() -> dict[str, dict]:
    return airportsdata.load("IATA")


def _by_city(place: str) -> str | None:
    """Best airport for a city name, preferring international airports."""
    city = place.strip().lower()
    matches = [
        (("international" in airport["name"].lower()), code)
        for code, airport in _airports().items()
        if airport["city"].lower() == city
    ]
    return max(matches)[1] if matches else None


def resolve_iata(code: str | None, place: str | None = None) -> str | None:
    """Return a valid IATA code from the LLM's suggestion, or from the place name."""
    candidate = (code or "").strip().upper()

    if len(candidate) == 3 and candidate in _airports():
        return candidate

    return _by_city(place) if place else None


def metro_airports(code: str) -> set[str]:
    """All airports serving the same city, e.g. NRT -> {NRT, HND} for Tokyo."""
    airport = _airports().get(code)

    if not airport or not airport["city"]:
        return {code}

    return {
        other_code
        for other_code, other in _airports().items()
        if other["city"] == airport["city"] and other["country"] == airport["country"]
    }


def airport_label(code: str) -> str:
    airport = _airports().get(code)
    return f"{code} ({airport['name']}, {airport['city']})" if airport else code
