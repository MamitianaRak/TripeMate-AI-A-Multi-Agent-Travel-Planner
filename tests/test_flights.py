import json

import pytest

from app.agents.airports import airport_label, metro_airports, resolve_iata
from app.agents.text import route_departures
from tests.fakes import DEPARTURES, departure


def test_resolve_iata_accepts_valid_code():
    assert resolve_iata("nrt") == "NRT"


def test_resolve_iata_rejects_invented_code_and_falls_back_to_city():
    assert resolve_iata("ZZZ", "Dhaka") == "DAC"


def test_resolve_iata_prefers_international_airport_for_a_city():
    assert resolve_iata("", "Tokyo") in {"NRT", "HND"}


def test_resolve_iata_returns_none_when_unknown():
    assert resolve_iata("", "Atlantis") is None
    assert resolve_iata(None) is None


def test_metro_airports_groups_city_airports():
    assert {"NRT", "HND"} <= metro_airports("NRT")


def test_airport_label():
    assert airport_label("NRT") == "NRT (Narita International Airport, Tokyo)"


def _board(rows):
    return json.dumps({"ok": True, "count": len(rows), "data": rows})


def test_route_departures_filters_and_dedupes():
    text = route_departures(_board(DEPARTURES), {"NRT", "HND"})

    assert text.splitlines() == [
        "- BG376 Biman Bangladesh: departs 10:00, arrives 19:30 at NRT",
        "- JL052 Japan Airlines: departs 22:40, arrives 07:55 at HND",
    ]


def test_route_departures_caps_the_list():
    rows = [departure(f"XX{n}", "Air X", "NRT", f"{n:02d}:00", f"{n:02d}:30") for n in range(20)]
    assert len(route_departures(_board(rows), {"NRT"}, max_flights=8).splitlines()) == 8


def test_route_departures_empty_when_no_direct_flight():
    assert route_departures(_board(DEPARTURES), {"CDG"}) == ""


def test_route_departures_raises_on_mcp_error():
    with pytest.raises(RuntimeError, match="restricted"):
        route_departures('{"ok": false, "error": "function_access_restricted"}', {"NRT"})
