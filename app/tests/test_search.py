"""Tests for a search: when the sources are due, what is kept, what Google adds."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import date, datetime, timedelta
import json
import threading
from typing import Any
from unittest.mock import patch

import aiohttp

from flight_prices_engine.models import Hours, Leg
from flight_prices_engine.search import Search
from flight_prices_engine.sources import SourceBlocked, SourceError
from flight_prices_engine.sources.google import GoogleFlight, Place
from flight_prices_engine.store import Store

from .conftest import Clock, Ryanair, config, ryanair_payload


def _week(search: Search, number: int) -> dict[str, Any]:
    return search.result()["weeks"][number - 1]


async def test_ryanair_anywhere(make_search, ryanair: Ryanair) -> None:
    ryanair.answer(ryanair_payload())
    search = await make_search()
    # Two airports, two weeks.
    assert ryanair.call_count == 4

    result = search.result()
    assert result["currency"] == "EUR"
    week = result["weeks"][0]
    assert week["trips"][0]["price"] == 131.98
    assert (week["outbound_date"], week["return_date"]) == ("2026-11-06", "2026-11-08")
    # Both airports answered with the same fixture: one trip per destination is kept.
    assert week["destinations_found"] == 3
    first = week["trips"][0]
    assert first["city"] == "Varsavia"
    assert first["outbound"]["departure"] == "2026-11-06T19:00"
    assert first["return"]["flights"] == "FR1904"
    # The fixture is for 6 to 8 November only.
    assert result["weeks"][1]["trips"] == []
    assert result["sources"] == {
        "ryanair": {
            "last_attempt": "2026-11-04T10:00:00+00:00",
            "last_success": "2026-11-04T10:00:00+00:00",
            "error": None,
            # The same three fares for each airport and week, kept as found.
            "trips": 12,
            "running": False,
        }
    }


async def test_destinations_found_beyond_the_kept_trips(make_search, ryanair: Ryanair) -> None:
    payload = ryanair_payload()
    fare = payload["fares"][0]
    fares = []
    for number in range(50):
        copy = json.loads(json.dumps(fare))
        copy["outbound"]["arrivalAirport"]["iataCode"] = f"X{number:02d}"
        copy["outbound"]["arrivalAirport"]["city"] = {"name": f"City {number}"}
        copy["summary"]["price"]["value"] = 100 + number
        fares.append(copy)
    ryanair.answer({**payload, "fares": fares})
    week = _week(await make_search(), 1)
    assert week["destinations_found"] == 50
    # Forty kept, cheapest first.
    assert len(week["trips"]) == 40
    assert week["trips"][0]["price"] == 100


async def test_excluded_countries(make_search, ryanair: Ryanair) -> None:
    ryanair.answer(ryanair_payload())
    week = _week(await make_search(exclude_countries=["IT"]), 1)
    assert [(trip["city"], trip["country_code"]) for trip in week["trips"]] == [
        ("Varsavia", "PL"),
        ("Edimburgo", "GB"),
    ]
    assert week["destinations_found"] == 2


async def test_saved_results_survive_a_restart(
    make_search, ryanair: Ryanair, clock: Clock, store: Store, session: aiohttp.ClientSession
) -> None:
    ryanair.answer(ryanair_payload())
    await make_search()
    assert ryanair.call_count == 4

    clock.tick(timedelta(hours=1))
    again = Search("entry1", config(), store, session, clock)
    await again.load()
    await again.tick()
    # Not due yet: the saved trips are there, nothing is searched.
    assert ryanair.call_count == 4
    assert _week(again, 1)["trips"][0]["price"] == 131.98

    # Due after three hours.
    clock.tick(timedelta(hours=2, minutes=1))
    await again.tick()
    assert ryanair.call_count == 8


async def test_restore_from_the_integration(
    make_search, ryanair: Ryanair, clock: Clock, tmp_path: Any, session: aiohttp.ClientSession
) -> None:
    """What the integration saved before the app existed is used once, when the app has nothing."""
    ryanair.answer(ryanair_payload())
    first = await make_search()
    saved = json.loads((tmp_path / "searches" / "entry1" / "state.json").read_text(encoding="utf-8"))

    clock.tick(timedelta(hours=1))
    moved = Search("other", first.config, Store(tmp_path / "new"), session, clock)
    await moved.load(restore=saved)
    await moved.tick()
    assert ryanair.call_count == 4
    assert _week(moved, 1)["trips"][0]["price"] == 131.98


async def test_changed_search_searches_again(
    make_search, ryanair: Ryanair, store: Store, session: aiohttp.ClientSession, clock: Clock
) -> None:
    ryanair.answer(ryanair_payload())
    await make_search()
    changed = Search("entry1", config(outbound_from=18), store, session, clock)
    await changed.load()
    await changed.tick()
    assert ryanair.call_count == 8


async def test_more_weeks_search_at_once(
    make_search, ryanair: Ryanair, store: Store, session: aiohttp.ClientSession, clock: Clock
) -> None:
    ryanair.answer(ryanair_payload())
    await make_search()
    assert ryanair.call_count == 4
    # Fewer weeks: what was found is enough.
    fewer = Search("entry1", config(weeks=1), store, session, clock)
    await fewer.load()
    await fewer.tick()
    assert ryanair.call_count == 4
    # More weeks than the last search covered: two airports, three weeks, at once.
    more = Search("entry1", config(weeks=3), store, session, clock)
    await more.load()
    await more.tick()
    assert ryanair.call_count == 10
    assert len(more.result()["weeks"]) == 3


async def test_ryanair_failure_keeps_old_trips(make_search, ryanair: Ryanair, clock: Clock) -> None:
    ryanair.answer(ryanair_payload())
    search = await make_search()
    ryanair.answer(status=500)
    clock.tick(timedelta(hours=3, minutes=1))
    await search.tick()
    assert _week(search, 1)["trips"][0]["price"] == 131.98
    state = search.result()["sources"]["ryanair"]
    assert state["last_success"] == "2026-11-04T10:00:00+00:00"
    assert "500" in state["error"]
    # An error is tried again after half an hour, not at the next interval.
    calls = ryanair.call_count
    clock.tick(timedelta(minutes=31))
    await search.tick()
    assert ryanair.call_count == calls + 4


def _flight(
    origin: str,
    destination: str,
    day: date,
    hour: int,
    price: float,
    number: str,
    airline: str = "easyJet",
    place: Place | None = None,
) -> GoogleFlight:
    departure = datetime(day.year, day.month, day.day, hour, 0)
    return GoogleFlight(
        Leg(
            origin=origin,
            destination=destination,
            departure=departure,
            arrival=departure + timedelta(hours=2),
            flight_numbers=(number,),
            airline=airline,
        ),
        price,
        place=place,
    )


def _fake_google(blocked_after: int | None = None, failing: set[int] | None = None):
    calls: list[tuple] = []

    def search(day: date, origin: str, destination: str, hours: Hours, direct_only: bool) -> list[GoogleFlight]:
        calls.append((day, origin, destination))
        if blocked_after is not None and len(calls) > blocked_after:
            raise SourceBlocked("Google Flights asked to solve a captcha")
        if failing and len(calls) in failing:
            raise SourceError("timeout")
        if day.weekday() == 4:
            return [_flight(origin, destination, day, 20, 50 if origin == "MXP" else 70, "U21")]
        return [_flight(origin, destination, day, 18, 60, "U22")]

    return calls, search


@contextmanager
def google(search: Callable[..., Any], link: Any = "https://g") -> Generator[None]:
    link_patch = {"side_effect": link} if callable(link) else {"return_value": link}
    with (
        patch("flight_prices_engine.sources.google.GoogleSource.search", side_effect=search),
        patch("flight_prices_engine.sources.google.GoogleSource.link", **link_patch),
    ):
        yield


async def test_google_round(make_search, ryanair: Ryanair) -> None:
    calls, fake = _fake_google()
    with google(fake):
        search = await make_search(sources=["google"], destinations=["LIS"])
    # Two weeks, one destination, two airports, outbound and return.
    assert len(calls) == 8
    trip = _week(search, 1)["trips"][0]
    assert trip["price"] == 110
    assert (trip["origin"], trip["source"], trip["link"]) == ("MXP", "google", "https://g")
    assert search.result()["sources"]["google"]["running"] is False
    assert ryanair.call_count == 0


async def test_google_block_stops_the_round(make_search) -> None:
    calls, fake = _fake_google(blocked_after=2)
    with google(fake):
        search = await make_search(sources=["google"], destinations=["LIS"])
    assert len(calls) == 3
    # What came before the block is kept.
    assert _week(search, 1)["trips"][0]["price"] == 110
    state = search.result()["sources"]["google"]
    assert state["last_success"] is None
    assert "captcha" in state["error"]


async def test_google_single_error_goes_on(make_search) -> None:
    calls, fake = _fake_google(failing={1})
    with google(fake):
        search = await make_search(sources=["google"], destinations=["LIS"])
    # The first outbound failed, so its return was not searched.
    assert len(calls) == 7
    # Only BGY is left for the first week.
    assert _week(search, 1)["trips"][0]["price"] == 130
    assert search.result()["sources"]["google"]["last_success"] == "2026-11-04T10:00:00+00:00"


async def test_google_takes_names_from_ryanair(make_search, ryanair: Ryanair) -> None:
    ryanair.answer(ryanair_payload())
    _calls, fake = _fake_google()
    with google(fake):
        search = await make_search(sources=["ryanair", "google"], destinations=["PMO", "WWA"])
    # Google is cheaper everywhere: 50 + 60 from MXP, 70 + 60 from BGY.
    assert [
        (trip["destination"], trip["origin"], trip["city"], trip["country_code"], trip["source"])
        for trip in _week(search, 1)["trips"]
    ] == [
        ("PMO", "MXP", "Palermo", "IT", "google"),
        ("WWA", "MXP", "Varsavia", "PL", "google"),
        ("PMO", "BGY", "Palermo", "IT", "google"),
        ("WWA", "BGY", "Varsavia", "PL", "google"),
    ]


async def test_google_two_airlines_two_tickets(make_search) -> None:
    def fake(day: date, origin: str, destination: str, hours: Hours, direct_only: bool) -> list[GoogleFlight]:
        if day.weekday() == 4:
            return [_flight(origin, destination, day, 20, 40, "FR1", "Ryanair", Place("Londra", "Regno Unito", "GB"))]
        # Back with another airline in the first week, with the same one in the second.
        airline = "Wizz Air" if day.day == 8 else "Ryanair"
        return [_flight(origin, destination, day, 18, 60, "W1", airline, Place("Milano", "Italia", "IT"))]

    def link(legs: list[tuple], direct_only: bool) -> str:
        return " ".join(f"{day.day}:{origin}-{destination}" for day, origin, destination, _hours in legs)

    with google(fake, link):
        search = await make_search(sources=["google"], origins=["MXP"], destinations=["LON"], exclude_countries=["IT"])
    first = _week(search, 1)["trips"][0]
    assert (first["link"], first["return_link"]) == ("6:MXP-LON", "8:LON-MXP")
    # City and country from Google's page, so the countries left out apply to Google's trips too.
    assert (first["city"], first["country"], first["country_code"]) == ("Londra", "Regno Unito", "GB")
    second = _week(search, 2)["trips"][0]
    assert (second["link"], second["return_link"]) == ("13:MXP-LON 15:LON-MXP", None)


async def test_google_from_some_airports(make_search, ryanair: Ryanair) -> None:
    ryanair.answer(ryanair_payload())
    calls, fake = _fake_google()
    with google(fake):
        await make_search(sources=["ryanair", "google"], destinations=["PMO"], google_origins=["MXP"])
    # Ryanair from both airports, Google from Malpensa only: two weeks, outbound and return.
    assert ryanair.call_count == 4
    assert {call[1] for call in calls} == {"MXP", "PMO"}
    assert len(calls) == 4


async def test_ryanair_anywhere_google_list(make_search, ryanair: Ryanair) -> None:
    ryanair.answer(ryanair_payload())
    calls, fake = _fake_google()
    with google(fake):
        search = await make_search(
            sources=["ryanair", "google"], google_origins=["MXP"], google_destinations=["HAM"], weeks=1
        )
    assert {call[2] for call in calls} == {"HAM", "MXP"}
    # Ryanair still everywhere, Google adds Hamburg.
    assert [trip["destination"] for trip in _week(search, 1)["trips"]] == ["HAM", "WWA", "PMO", "EDI"]


async def test_close_during_google_saves_what_was_found(
    store: Store, session: aiohttp.ClientSession, clock: Clock
) -> None:
    """Stopping the app in the middle of a round keeps the weeks already searched."""
    reached, release = threading.Event(), threading.Event()

    def fake(day: date, origin: str, destination: str, hours: Hours, direct_only: bool) -> list[GoogleFlight]:
        if day > date(2026, 11, 8):
            # The app stops while this request is still waiting for Google.
            reached.set()
            release.wait(5)
            return []
        return [_flight(origin, destination, day, 20 if day.weekday() == 4 else 18, 50, "U21")]

    search = Search("entry1", config(sources=["google"], destinations=["LIS"], origins=["MXP"]), store, session, clock)
    await search.load()
    with google(fake):
        await search.tick()
        await asyncio.to_thread(reached.wait, 5)
        await search.close()
        release.set()
    saved = await store.load_state("entry1")
    assert len(saved["sources"]["google"]["trips"]) == 1
    assert saved["sources"]["google"]["error"] is None


async def test_unreadable_saved_results_start_empty(
    ryanair: Ryanair, store: Store, session: aiohttp.ClientSession, clock: Clock
) -> None:
    ryanair.answer(ryanair_payload())
    search = Search("entry1", config(), store, session, clock)
    await search.load(restore={"sources": {"ryanair": {"trips": [{"source": "ryanair"}]}}, "names": []})
    await search.tick()
    assert _week(search, 1)["trips"][0]["price"] == 131.98


async def test_restored_results_survive_a_restart_before_any_search(
    make_search, ryanair: Ryanair, clock: Clock, tmp_path: Any, session: aiohttp.ClientSession
) -> None:
    """The results of version 0, sent once, are saved even when nothing is due before the app restarts."""
    ryanair.answer(ryanair_payload())
    await make_search()
    saved = json.loads((tmp_path / "searches" / "entry1" / "state.json").read_text(encoding="utf-8"))
    store = Store(tmp_path / "moved")

    clock.tick(timedelta(hours=1))
    moved = Search("entry1", config(), store, session, clock)
    await moved.load(restore=saved)
    # The app restarts before any source is due: the client no longer sends what it had.
    again = Search("entry1", config(), store, session, clock)
    await again.load()
    await again.tick()
    assert ryanair.call_count == 4
    assert _week(again, 1)["trips"][0]["price"] == 131.98
