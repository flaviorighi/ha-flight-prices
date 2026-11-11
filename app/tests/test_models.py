"""Tests for the shared data."""

from __future__ import annotations

from datetime import date, datetime

from flight_prices_engine.models import (
    Hours,
    Leg,
    SearchParams,
    SourceState,
    Trip,
    cheapest_per_route,
)

from .conftest import OPTIONS


def _trip(destination: str, price: float, source: str = "ryanair", origin: str = "BGY") -> Trip:
    return Trip(
        source=source,
        destination=destination,
        city=None,
        country=None,
        price=price,
        currency="EUR",
        outbound=Leg(
            origin=origin,
            destination=destination,
            departure=datetime(2026, 11, 6, 19, 0),
            arrival=datetime(2026, 11, 6, 21, 0),
            flight_numbers=("FR1",),
            airline="Ryanair",
        ),
        inbound=Leg(
            origin=destination,
            destination=origin,
            departure=datetime(2026, 11, 8, 15, 0),
            arrival=datetime(2026, 11, 8, 17, 0),
            flight_numbers=("FR2",),
            airline="Wizz Air",
        ),
        link="https://example.com",
    )


def test_upcoming_weeks() -> None:
    params = SearchParams.from_options(OPTIONS)
    # From a Wednesday, a Friday (the same day counts) and a Saturday.
    weeks = params.upcoming_weeks(date(2026, 11, 4))
    assert [(week.number, week.outbound, week.inbound) for week in weeks] == [
        (1, date(2026, 11, 6), date(2026, 11, 8)),
        (2, date(2026, 11, 13), date(2026, 11, 15)),
    ]
    assert params.upcoming_weeks(date(2026, 11, 6))[0].outbound == date(2026, 11, 6)
    assert params.upcoming_weeks(date(2026, 11, 7))[0].outbound == date(2026, 11, 13)


def test_return_before_outbound_day_is_the_next_week() -> None:
    params = SearchParams.from_options({**OPTIONS, "outbound_day": 5, "return_day": 1})
    week = params.upcoming_weeks(date(2026, 11, 4))[0]
    assert (week.outbound, week.inbound) == (date(2026, 11, 7), date(2026, 11, 10))


def test_hours() -> None:
    evening = Hours(19, 24)
    assert evening.contains(datetime(2026, 11, 6, 19, 0))
    assert evening.contains(datetime(2026, 11, 6, 23, 59))
    assert not evening.contains(datetime(2026, 11, 6, 18, 59))
    assert (evening.start_text, evening.end_text) == ("19:00", "23:59")
    assert not Hours(14, 18).contains(datetime(2026, 11, 8, 18, 0))


def test_fingerprint_changes_with_the_search() -> None:
    params = SearchParams.from_options(OPTIONS)
    assert params.fingerprint("ryanair") == SearchParams.from_options({**OPTIONS, "weeks": 5}).fingerprint("ryanair")
    assert params.fingerprint("ryanair") != SearchParams.from_options({**OPTIONS, "outbound_from": 18}).fingerprint(
        "ryanair"
    )
    # Ryanair always flies direct, Google not necessarily.
    other = SearchParams.from_options({**OPTIONS, "direct_only": False})
    assert params.fingerprint("ryanair") == other.fingerprint("ryanair")
    assert params.fingerprint("google") != other.fingerprint("google")


def test_google_origins() -> None:
    params = SearchParams.from_options({**OPTIONS, "google_origins": ["MXP"]})
    assert params.origins_for("ryanair") == ("MXP", "BGY")
    assert params.origins_for("google") == ("MXP",)
    assert SearchParams.from_options(OPTIONS).origins_for("google") == ("MXP", "BGY")
    # Only Google searches again when its airports change.
    assert params.fingerprint("ryanair") == SearchParams.from_options(OPTIONS).fingerprint("ryanair")
    assert params.fingerprint("google") != SearchParams.from_options(OPTIONS).fingerprint("google")


def test_google_destinations() -> None:
    params = SearchParams.from_options({**OPTIONS, "google_destinations": ["LIS", "PAR"]})
    assert params.destinations_for("ryanair") == ()
    assert params.destinations_for("google") == ("LIS", "PAR")
    assert params.all_destinations == ("LIS", "PAR")
    # Ryanair keeps searching anywhere: its saved trips stay valid.
    assert params.fingerprint("ryanair") == SearchParams.from_options(OPTIONS).fingerprint("ryanair")


def test_one_trip_per_destination_and_airport() -> None:
    trips = [_trip("BCN", 90), _trip("BCN", 95), _trip("BCN", 70, "google", "MXP"), _trip("LIS", 80)]
    assert [(trip.destination, trip.origin, trip.price) for trip in cheapest_per_route(trips)] == [
        ("BCN", "MXP", 70),
        ("LIS", "BGY", 80),
        ("BCN", "BGY", 90),
    ]


def test_trip_survives_storage() -> None:
    trip = _trip("BCN", 70)
    state = SourceState(fingerprint="x", trips=[trip])
    assert SourceState.from_dict(state.as_dict()).trips == [trip]
    assert trip.airline == "Ryanair / Wizz Air"
    assert trip.as_attributes()["outbound"]["departure"] == "2026-11-06T19:00"
