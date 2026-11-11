"""Fixtures for the engine tests: no Home Assistant, no network."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import aiohttp
from aiohttp import web
import pytest
from yarl import URL

from flight_prices_engine.search import Search, SearchConfig
from flight_prices_engine.store import Store

FIXTURES = Path(__file__).parent / "fixtures"
# A Wednesday: the first week is Friday 6 to Sunday 8 November 2026, as in the fixture.
NOW = datetime.fromisoformat("2026-11-04T10:00:00+00:00")

OPTIONS: dict[str, Any] = {
    "origins": ["MXP", "BGY"],
    "destinations": [],
    "exclude_countries": [],
    "sources": ["ryanair"],
    "google_origins": [],
    "google_destinations": [],
    "weeks": 2,
    "outbound_day": 4,
    "outbound_from": 19,
    "outbound_to": 24,
    "return_day": 6,
    "return_from": 14,
    "return_to": 24,
    "direct_only": True,
}


def ryanair_payload() -> dict[str, Any]:
    """A real answer from BGY for 6 to 8 November 2026: Warsaw Modlin, Palermo, Edinburgh."""
    return json.loads((FIXTURES / "ryanair_bgy.json").read_text(encoding="utf-8"))


def config(**options: Any) -> SearchConfig:
    return SearchConfig(options={**OPTIONS, **options}, currency="EUR", language="it", time_zone="Europe/Rome")


def body(**options: Any) -> dict[str, Any]:
    """A search as the integration sends it."""
    return config(**options).as_dict()


class Clock:
    """The time the engine sees, moved by the tests."""

    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now

    def tick(self, delta: timedelta) -> None:
        self.now += delta


class Ryanair:
    """Ryanair's fare finder on a local server, answering with what the test sets."""

    def __init__(self) -> None:
        self.payload: dict[str, Any] = {}
        self.status = 200
        self.calls: list[URL] = []

    def answer(self, payload: dict[str, Any] | None = None, status: int = 200) -> None:
        self.payload = payload if payload is not None else {}
        self.status = status

    @property
    def call_count(self) -> int:
        return len(self.calls)

    async def handle(self, request: web.Request) -> web.Response:
        self.calls.append(request.url)
        if self.status != 200:
            return web.Response(status=self.status)
        return web.json_response(self.payload)


@pytest.fixture(autouse=True)
def no_delays() -> Generator[None]:
    """The pauses between requests are for the real services only."""
    with (
        patch("flight_prices_engine.const.RYANAIR_DELAY", 0),
        patch("flight_prices_engine.const.GOOGLE_DELAY", (0, 0)),
    ):
        yield


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path)


@pytest.fixture
async def ryanair(aiohttp_server: Any) -> AsyncGenerator[Ryanair]:
    fake = Ryanair()
    app = web.Application()
    app.router.add_get("/farfnd/v4/roundTripFares", fake.handle)
    server = await aiohttp_server(app)
    with patch("flight_prices_engine.sources.ryanair.URL", str(server.make_url("/farfnd/v4/roundTripFares"))):
        yield fake


@pytest.fixture
async def session() -> AsyncGenerator[aiohttp.ClientSession]:
    async with aiohttp.ClientSession() as client:
        yield client


@pytest.fixture
async def make_search(store: Store, session: aiohttp.ClientSession, clock: Clock) -> AsyncGenerator[Any]:
    """A search loaded and searched once, Google round included."""
    searches: list[Search] = []

    async def make(search_id: str = "entry1", **options: Any) -> Search:
        search = Search(search_id, config(**options), store, session, clock)
        searches.append(search)
        await search.load()
        await search.tick()
        await search.wait_google()
        return search

    yield make
    for search in searches:
        await search.close()
