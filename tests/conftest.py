"""Fixtures for the integration tests: the app is faked, its counting is the real one."""

from __future__ import annotations

from collections.abc import Generator
import copy
import re
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker, AiohttpClientMockResponse
from yarl import URL

from custom_components.flight_prices.const import (
    CONF_DESTINATIONS,
    CONF_DIRECT_ONLY,
    CONF_EXCLUDE_COUNTRIES,
    CONF_GOOGLE_DESTINATIONS,
    CONF_GOOGLE_ORIGINS,
    CONF_ORIGINS,
    CONF_OUTBOUND_DAY,
    CONF_OUTBOUND_FROM,
    CONF_OUTBOUND_TO,
    CONF_RETURN_DAY,
    CONF_RETURN_FROM,
    CONF_RETURN_TO,
    CONF_SOURCES,
    CONF_URL,
    CONF_WEEKS,
    DOMAIN,
)
from flight_prices_engine.requests import count_requests
from homeassistant.core import HomeAssistant

APP = "http://flight-prices.test:8765"

OPTIONS: dict[str, Any] = {
    CONF_ORIGINS: ["MXP", "BGY"],
    CONF_DESTINATIONS: [],
    CONF_EXCLUDE_COUNTRIES: [],
    CONF_SOURCES: ["ryanair"],
    CONF_GOOGLE_ORIGINS: [],
    CONF_GOOGLE_DESTINATIONS: [],
    CONF_WEEKS: 2,
    CONF_OUTBOUND_DAY: 4,
    CONF_OUTBOUND_FROM: 19,
    CONF_OUTBOUND_TO: 24,
    CONF_RETURN_DAY: 6,
    CONF_RETURN_FROM: 14,
    CONF_RETURN_TO: 24,
    CONF_DIRECT_ONLY: True,
}


def trip(destination: str, city: str, code: str, price: float, origin: str = "BGY", source: str = "ryanair") -> dict:
    """A trip as the app describes it."""
    return {
        "destination": destination,
        "city": city,
        "country": None,
        "country_code": code,
        "origin": origin,
        "price": price,
        "airline": "Ryanair",
        "source": source,
        "outbound": {
            "from": origin,
            "to": destination,
            "departure": "2026-11-06T19:00",
            "arrival": "2026-11-06T21:00",
            "flights": "FR3341",
            "airline": "Ryanair",
            "stops": 0,
        },
        "return": {
            "from": destination,
            "to": origin,
            "departure": "2026-11-08T18:00",
            "arrival": "2026-11-08T20:00",
            "flights": "FR1904",
            "airline": "Ryanair",
            "stops": 0,
        },
        "link": f"https://www.ryanair.com/{destination}",
        "return_link": None,
    }


def source_state(last_success: str | None = "2026-11-04T10:00:00+00:00", error: str | None = None) -> dict:
    return {
        "last_attempt": "2026-11-04T10:00:00+00:00",
        "last_success": last_success,
        "error": error,
        "trips": 3,
        "running": False,
    }


def result(**sources: dict) -> dict[str, Any]:
    """What the app answers for the search in OPTIONS: three trips the first week, none the second."""
    return {
        "id": "entry",
        "updated": "2026-11-04T10:00:00+00:00",
        "currency": "EUR",
        "weeks": [
            {
                "number": 1,
                "outbound_date": "2026-11-06",
                "return_date": "2026-11-08",
                "destinations_found": 3,
                "trips": [
                    trip("WWA", "Varsavia", "PL", 131.98),
                    trip("PMO", "Palermo", "IT", 177.6),
                    trip("EDI", "Edimburgo", "GB", 184.88),
                ],
            },
            {
                "number": 2,
                "outbound_date": "2026-11-13",
                "return_date": "2026-11-15",
                "destinations_found": 0,
                "trips": [],
            },
        ],
        "sources": sources or {"ryanair": source_state()},
    }


class FakeApp:
    """The Flight Prices app as the integration sees it."""

    def __init__(self, mock: AiohttpClientMocker) -> None:
        self.answer = result()
        # The searches the app runs, as they were sent.
        self.searches: dict[str, dict[str, Any]] = {}
        self.puts: list[dict[str, Any]] = []
        self.deleted: list[str] = []
        self.online = True
        self.api = 1
        self.refuse: str | None = None
        self.mock = mock
        mock.get(f"{APP}/api/info", side_effect=self._info)
        mock.post(f"{APP}/api/requests", side_effect=self._requests)
        searches = re.compile(rf"^{re.escape(APP)}/api/searches/(\w+)$")
        mock.get(searches, side_effect=self._get)
        mock.put(searches, side_effect=self._put)
        mock.delete(searches, side_effect=self._delete)

    def _response(self, method: str, url: URL, json: Any = None, status: int = 200) -> AiohttpClientMockResponse:
        if not self.online:
            return AiohttpClientMockResponse(method, url, exc=aiohttp.ClientConnectionError("refused"))
        return AiohttpClientMockResponse(method, url, json=json, status=status)

    async def _info(self, method: str, url: URL, data: Any) -> AiohttpClientMockResponse:
        return self._response(method, url, {"version": "1.0.0b0", "api": self.api, "searches": sorted(self.searches)})

    async def _requests(self, method: str, url: URL, data: Any) -> AiohttpClientMockResponse:
        return self._response(method, url, count_requests(data["options"]).as_dict())

    async def _get(self, method: str, url: URL, data: Any) -> AiohttpClientMockResponse:
        search_id = url.path.rsplit("/", 1)[1]
        if search_id not in self.searches:
            return self._response(method, url, {"error": "not_found"}, 404)
        return self._response(method, url, copy.deepcopy(self.answer))

    async def _put(self, method: str, url: URL, data: Any) -> AiohttpClientMockResponse:
        if self.refuse:
            return self._response(method, url, {"error": self.refuse, "message": self.refuse}, 400)
        search_id = url.path.rsplit("/", 1)[1]
        self.searches[search_id] = data
        self.puts.append(data)
        return self._response(method, url, copy.deepcopy(self.answer))

    async def _delete(self, method: str, url: URL, data: Any) -> AiohttpClientMockResponse:
        search_id = url.path.rsplit("/", 1)[1]
        self.searches.pop(search_id, None)
        self.deleted.append(search_id)
        return AiohttpClientMockResponse(method, url, status=204) if self.online else self._response(method, url)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load the integration from custom_components."""


@pytest.fixture(autouse=True)
def frontend(hass: HomeAssistant) -> Generator[MagicMock]:
    """frontend and http as Home Assistant has them; the frontend package is not installed for tests."""
    hass.config.components.update({"frontend", "http"})
    hass.http = MagicMock(async_register_static_paths=AsyncMock())
    with patch("custom_components.flight_prices.add_extra_js_url") as add:
        yield add


@pytest.fixture
def app(aioclient_mock: AiohttpClientMocker) -> FakeApp:
    return FakeApp(aioclient_mock)


def make_entry(version: int = 2, url: str | None = APP, **options: Any) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Weekend",
        version=version,
        data={CONF_URL: url} if url else {},
        options={**OPTIONS, **options},
    )
