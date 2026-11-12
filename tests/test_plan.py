"""Tests for the requests a round makes, which the coordinator runs and the options count."""

from __future__ import annotations

from datetime import date

from custom_components.flight_prices.config_flow import count_requests
from custom_components.flight_prices.models import SearchParams
from custom_components.flight_prices.sources.google import GoogleRequest, plan as google_plan
from custom_components.flight_prices.sources.ryanair import RyanairRequest, plan as ryanair_plan

from .conftest import OPTIONS

TODAY = date(2026, 11, 2)
OPTIONS_BOTH = {
    **OPTIONS,
    "origins": ["WRO", "KTW"],
    "destinations": ["LIS", "PMO", "STN"],
    "sources": ["ryanair", "google"],
    "weeks": 3,
}


def test_ryanair_plan_is_one_request_per_week_and_airport() -> None:
    params = SearchParams.from_options(OPTIONS_BOTH)
    weeks = params.upcoming_weeks(TODAY)
    requests = ryanair_plan(params, weeks)
    assert requests == [RyanairRequest(week, origin) for week in weeks for origin in ("WRO", "KTW")]
    assert requests[0].key == (weeks[0].outbound.isoformat(), "WRO")
    assert len({request.key for request in requests}) == 6


def test_google_plan_is_week_then_destination_then_airport() -> None:
    params = SearchParams.from_options(OPTIONS_BOTH)
    weeks = params.upcoming_weeks(TODAY)
    requests = google_plan(params, weeks)
    assert len(requests) == 3 * 3 * 2
    assert requests[:3] == [
        GoogleRequest(weeks[0], "WRO", "LIS"),
        GoogleRequest(weeks[0], "KTW", "LIS"),
        GoogleRequest(weeks[0], "WRO", "PMO"),
    ]
    assert sum(request.max_requests for request in requests) == 36


def test_google_has_its_own_airports_and_destinations() -> None:
    params = SearchParams.from_options({**OPTIONS_BOTH, "google_origins": ["WRO"], "google_destinations": ["LIS"]})
    weeks = params.upcoming_weeks(TODAY)
    assert google_plan(params, weeks) == [GoogleRequest(week, "WRO", "LIS") for week in weeks]
    # Ryanair keeps the airports of the search.
    assert len(ryanair_plan(params, weeks)) == 6


def test_google_without_destinations_has_nothing_to_search() -> None:
    params = SearchParams.from_options({**OPTIONS_BOTH, "destinations": []})
    assert google_plan(params, params.upcoming_weeks(TODAY)) == []


def test_the_options_count_the_same_requests() -> None:
    requests = count_requests(OPTIONS_BOTH)
    params = SearchParams.from_options(OPTIONS_BOTH)
    weeks = params.upcoming_weeks(TODAY)
    assert requests.google_round == sum(request.max_requests for request in google_plan(params, weeks)) == 36
    assert requests.ryanair_round == len(ryanair_plan(params, weeks)) == 6
