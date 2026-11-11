"""Tests for Ryanair and Google Flights."""

from __future__ import annotations

import base64
from datetime import date, datetime
import json
from typing import Any
from unittest.mock import MagicMock, patch

import aiohttp
import pytest
from yarl import URL

from flight_prices_engine.models import Hours
from flight_prices_engine.sources import SourceBlocked, SourceError
from flight_prices_engine.sources.google import GoogleSource, Place, city_from_airport, parse_page
from flight_prices_engine.sources.ryanair import RyanairSource

from .conftest import Ryanair, ryanair_payload

OUT, BACK = date(2026, 11, 6), date(2026, 11, 8)
EVENING, AFTERNOON = Hours(19, 24), Hours(14, 24)


async def test_ryanair_anywhere(session: aiohttp.ClientSession, ryanair: Ryanair) -> None:
    ryanair.answer(ryanair_payload())
    source = RyanairSource(session, "EUR", "it-IT")
    trips = await source.search("BGY", OUT, BACK, EVENING, AFTERNOON)

    url: URL = ryanair.calls[0]
    assert dict(url.query) == {
        "departureAirportIataCode": "BGY",
        "outboundDepartureDateFrom": "2026-11-06",
        "outboundDepartureDateTo": "2026-11-06",
        "inboundDepartureDateFrom": "2026-11-08",
        "inboundDepartureDateTo": "2026-11-08",
        "outboundDepartureTimeFrom": "19:00",
        "outboundDepartureTimeTo": "23:59",
        "inboundDepartureTimeFrom": "14:00",
        "inboundDepartureTimeTo": "23:59",
        "currency": "EUR",
        "market": "it-it",
    }
    # Grouped by city when the airport has one (Warsaw Modlin is WWA).
    assert [(trip.destination, trip.city, trip.price) for trip in trips] == [
        ("WWA", "Varsavia", 131.98),
        ("PMO", "Palermo", 177.6),
        ("EDI", "Edimburgo", 184.88),
    ]
    warsaw = trips[0]
    assert warsaw.outbound.flight_numbers == ("FR3341",)
    assert warsaw.outbound.departure == datetime(2026, 11, 6, 19, 0)
    assert warsaw.inbound.origin == "WMI"
    assert warsaw.link.startswith("https://www.ryanair.com/it/it/trip/flights/select?")
    assert "originIata=BGY&destinationIata=WMI" in warsaw.link


async def test_ryanair_list_matches_airport_or_city(session: aiohttp.ClientSession, ryanair: Ryanair) -> None:
    ryanair.answer(ryanair_payload())
    source = RyanairSource(session, "EUR", "en")
    trips = await source.search("BGY", OUT, BACK, EVENING, AFTERNOON, ["wwa", "PMO", "LIS"])
    assert [trip.destination for trip in trips] == ["WWA", "PMO"]
    assert "/gb/en/" in trips[0].link


@pytest.mark.parametrize(("status", "error"), [(429, SourceBlocked), (403, SourceBlocked), (500, SourceError)])
async def test_ryanair_errors(
    session: aiohttp.ClientSession, ryanair: Ryanair, status: int, error: type[Exception]
) -> None:
    ryanair.answer(status=status)
    source = RyanairSource(session, "EUR", "it")
    with pytest.raises(error):
        await source.search("BGY", OUT, BACK, EVENING, AFTERNOON)


def segment(
    origin: str, destination: str, day: list[int], dep: list[Any], arr: list[Any], code: str, number: str
) -> list:
    seg: list[Any] = [None] * 33
    seg[3], seg[6], seg[8], seg[10] = origin, destination, dep, arr
    seg[4], seg[5] = f"Aeroporto di {origin}", f"Aeroporto di {destination}-Centro"
    seg[20], seg[21] = day, day
    seg[22] = [code, number, None, {"U2": "easyJet", "FR": "Ryanair", "AZ": "ITA"}[code]]
    return seg


def item(segments: list[list], price: int | None, airlines: list[str]) -> list:
    info: list[Any] = [None] * 25
    info[1], info[2] = airlines, segments
    return [info, [[None, price], "token"]]


# The places of a search as Google sends them, pictures left out: origins, then destinations.
PLACES = [
    [
        [[["MXP", 0], "Aeroporto di Milano Malpensa", ["/m/0947l", "Milano"], [45.63, 8.72], "IT", 0, "Italia"]],
        [[["/m/05qtj", 4], "Parigi", ["/m/05qtj", "Parigi", "Torre Eiffel"], [48.86, 2.35], "fr", None, "Francia"]],
    ]
]


def page(best: list | None, other: list | None, places: list | None = None) -> str:
    payload: list[Any] = [None] * 31
    payload[1] = places
    payload[2] = [best] if best else None
    payload[3] = [other] if other else None
    script = f"AF_initDataCallback({{key: 'ds:1', hash: '1', data:{json.dumps(payload)}, sideChannel: {{}}}});"
    return f'<html><body><script class="ds:1" nonce="x">{script}</script></body></html>'


DAY = [2026, 11, 6]
PAGE = page(
    best=[item([segment("MXP", "LIS", DAY, [21, 10], [23, 5], "U2", "7698")], 229, ["easyJet"])],
    other=[
        item([segment("MXP", "LIS", DAY, [19], [None, 31], "FR", "100")], 99, ["Ryanair"]),
        item([segment("MXP", "LIS", DAY, [18, 30], [21], "FR", "200")], 50, ["Ryanair"]),
        item([segment("MXP", "LIS", DAY, [20], [22], "FR", "300")], None, ["Ryanair"]),
        item(
            [
                segment("MXP", "FCO", DAY, [19, 15], [20, 20], "AZ", "1"),
                segment("FCO", "LIS", DAY, [21], [23], "AZ", "2"),
            ],
            150,
            ["ITA"],
        ),
    ],
)


def test_parse_page_reads_best_and_other_flights() -> None:
    flights = parse_page(PAGE)
    assert [(f.leg.flight_numbers, f.price, f.leg.stops) for f in flights] == [
        (("U27698",), 229.0, 0),
        (("FR100",), 99.0, 0),
        (("FR200",), 50.0, 0),
        (("AZ1", "AZ2"), 150.0, 1),
    ]
    assert flights[1].leg.departure == datetime(2026, 11, 6, 19, 0)
    assert flights[1].leg.arrival == datetime(2026, 11, 6, 0, 31)
    assert flights[3].leg.destination == "LIS"
    assert flights[0].leg.airline == "easyJet"
    assert flights[0].destination_name == "Aeroporto di LIS-Centro"


@pytest.mark.parametrize(
    ("airport", "city"),
    [
        ("Aeroporto di Lisbona-Portela", "Lisbona"),
        ("Aeroporto internazionale di Amburgo", "Amburgo"),
        ("Aeroporto di Londra-Gatwick", "Londra"),
        ("Lisbon Humberto Delgado Airport", "Lisbon Humberto Delgado"),
        ("Flughafen Hamburg", "Hamburg"),
        (None, None),
    ],
)
def test_city_from_airport(airport: str | None, city: str | None) -> None:
    assert city_from_airport(airport) == city


def test_parse_page_reads_the_place() -> None:
    flight = item([segment("MXP", "CDG", DAY, [20], [22], "U2", "1")], 64, ["easyJet"])
    flights = parse_page(page(None, [flight], PLACES))
    assert flights[0].place == Place(city="Parigi", country="Francia", country_code="FR")
    # A page without places still gives its flights.
    assert parse_page(PAGE)[0].place is None
    assert parse_page(page(None, None, [[[], [["?"]]]])) == []


def test_parse_page_without_flights() -> None:
    assert parse_page(page(None, None)) == []
    with pytest.raises(SourceBlocked):
        parse_page("<html><body>Something else</body></html>")


@pytest.mark.parametrize("direct_only", [True, False])
def test_google_search_keeps_the_hours(direct_only: bool) -> None:
    source = GoogleSource("EUR", "it-IT")
    with patch.object(source, "_fetch", return_value=PAGE) as fetch:
        flights = source.search(OUT, "MXP", "LIS", EVENING, direct_only)
    assert fetch.call_args.args[0]["curr"] == "EUR"
    # 18:30 is too early; cheapest first.
    expected = [("FR100",), ("AZ1", "AZ2"), ("U27698",)] if not direct_only else [("FR100",), ("U27698",)]
    assert [f.leg.flight_numbers for f in flights] == expected


@pytest.mark.parametrize(
    ("status", "location", "error"),
    [
        (302, "https://consent.google.com/m?continue=x", SourceBlocked),
        (302, "https://www.google.com/sorry/index?continue=x", SourceBlocked),
        (429, "", SourceBlocked),
        (500, "", SourceError),
    ],
)
def test_google_refusals(status: int, location: str, error: type[Exception]) -> None:
    source = GoogleSource("EUR", "it")
    response = MagicMock(status_code=status, headers={"location": location}, text="")
    with patch("flight_prices_engine.sources.google.Client") as client, pytest.raises(error):
        client.return_value.get.return_value = response
        source.search(OUT, "MXP", "LIS", EVENING, True)
    # The consent cookies go with every request.
    assert "SOCS=" in client.return_value.get.call_args.kwargs["headers"]["cookie"]


def _search(link: str) -> bytes:
    tfs = link.split("tfs=")[1].split("&")[0]
    return base64.urlsafe_b64decode(tfs + "=" * (-len(tfs) % 4))


def test_google_link() -> None:
    source = GoogleSource("EUR", "it-IT")
    there, back = (OUT, "MXP", "LIS", EVENING), (BACK, "LIS", "MXP", AFTERNOON)
    link = source.link([there, back], True)
    assert link.startswith("https://www.google.com/travel/flights/search?tfs=")
    assert link.endswith("&hl=it&curr=EUR")
    both = _search(link)
    assert b"2026-11-06" in both
    assert b"2026-11-08" in both
    # One leg is a one-way search.
    one = _search(source.link([there], True))
    assert b"2026-11-06" in one
    assert b"2026-11-08" not in one
    # The hours and the stops go into the search, as in the searches that found the trip.
    assert _search(source.link([(OUT, "MXP", "LIS", Hours(0, 24))], True)) != one
    assert _search(source.link([there], False)) != one
    with patch("flight_prices_engine.sources.google.create_query") as create:
        source.link([there, back], True)
    kwargs = create.call_args.kwargs
    assert kwargs["trip"] == "round-trip"
    assert kwargs["max_stops"] == 0
    assert [(f.earliest_departure_hour, f.latest_departure_hour) for f in kwargs["flights"]] == [(19, None), (14, None)]
