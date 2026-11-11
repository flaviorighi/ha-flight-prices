"""Tests for the HTTP API."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import AsyncGenerator
from datetime import timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

import aiohttp
from aiohttp.test_utils import TestClient
import pytest

from flight_prices_engine import __version__
from flight_prices_engine.server import ENGINE, Engine, create_app
from flight_prices_engine.store import Store

from .conftest import Clock, Ryanair, body, ryanair_payload


@pytest.fixture
async def client(
    aiohttp_client: Any, tmp_path: Path, session: aiohttp.ClientSession, clock: Clock, ryanair: Ryanair
) -> AsyncGenerator[TestClient]:
    ryanair.answer(ryanair_payload())
    yield await aiohttp_client(create_app(Engine(Store(tmp_path), session, clock)))


async def _searched(client: TestClient, search_id: str = "entry1") -> dict[str, Any]:
    """The answer once Ryanair has been searched: a new search starts in the background."""
    for _ in range(500):
        response = await client.get(f"/api/searches/{search_id}")
        result = await response.json()
        if result["sources"]["ryanair"]["last_success"]:
            return result
        await asyncio.sleep(0.01)
    raise AssertionError("never searched")


async def test_info(client: TestClient) -> None:
    response = await client.get("/api/info")
    assert response.status == 200
    assert await response.json() == {
        "version": __version__,
        "api": 1,
        "searches": [],
        "google": {"limit": 300, "day": 0, "last_24h": 0},
    }


async def test_put_get_delete(client: TestClient, ryanair: Ryanair, tmp_path: Path) -> None:
    response = await client.put("/api/searches/entry1", json=body())
    assert response.status == 200
    assert (await response.json())["id"] == "entry1"

    result = await _searched(client)
    assert result["weeks"][0]["trips"][0]["price"] == 131.98
    assert ryanair.call_count == 4
    assert (tmp_path / "searches" / "entry1" / "config.json").exists()
    assert (await (await client.get("/api/info")).json())["searches"] == ["entry1"]

    # The same search sent again, as at every start of Home Assistant: nothing is searched again.
    response = await client.put("/api/searches/entry1", json=body())
    assert response.status == 200
    await asyncio.sleep(0.05)
    assert ryanair.call_count == 4

    response = await client.delete("/api/searches/entry1")
    assert response.status == 204
    assert not (tmp_path / "searches" / "entry1").exists()
    assert (await client.get("/api/searches/entry1")).status == 404


async def test_changed_search_restarts(client: TestClient, ryanair: Ryanair) -> None:
    await client.put("/api/searches/entry1", json=body())
    await _searched(client)
    await client.put("/api/searches/entry1", json=body(outbound_from=18))
    for _ in range(500):
        if ryanair.call_count == 8:
            break
        await asyncio.sleep(0.01)
    assert ryanair.call_count == 8


async def test_not_running_after_a_restart(
    aiohttp_client: Any, client: TestClient, tmp_path: Path, session: aiohttp.ClientSession, clock: Clock
) -> None:
    """A restarted app answers 404 until the client sends the search again; nothing is searched again."""
    await client.put("/api/searches/entry1", json=body())
    await _searched(client)
    await client.app[ENGINE].close()

    restarted = await aiohttp_client(create_app(Engine(Store(tmp_path), session, clock)))
    assert (await restarted.get("/api/searches/entry1")).status == 404
    response = await restarted.put("/api/searches/entry1", json=body())
    assert (await response.json())["weeks"][0]["trips"][0]["price"] == 131.98


async def test_google_limit(client: TestClient) -> None:
    many = body(sources=["google"], destinations=[f"A{n:02d}" for n in range(20)], weeks=8)
    response = await client.put("/api/searches/entry1", json=many)
    assert response.status == 400
    assert (await response.json())["error"] == "google_too_many"
    short = body(sources=["google"], destinations=["LIS"], google_interval=6)
    response = await client.put("/api/searches/entry1", json=short)
    assert (await response.json())["error"] == "google_interval_too_short"


@pytest.mark.parametrize(
    "sent",
    [
        {"options": {"origins": ["MXP"]}},
        {**body(), "time_zone": "Mars/Base"},
        {**body(), "options": {"sources": ["ryanair"]}},
        {**body(ryanair_interval="often")},
        {**body(google_interval=0)},
        [1, 2],
    ],
)
async def test_invalid_search(client: TestClient, sent: Any) -> None:
    response = await client.put("/api/searches/entry1", json=sent)
    assert response.status == 400


async def test_invalid_id(client: TestClient) -> None:
    assert (await client.get("/api/searches/..%2Fsecrets")).status in (400, 404)
    assert (await client.put("/api/searches/a.b", json=body())).status == 400


async def test_requests(client: TestClient) -> None:
    options = body(sources=["ryanair", "google"], destinations=["LIS", "PAR"], weeks=8)["options"]
    response = await client.post("/api/requests", json={"options": options})
    assert await response.json() == {
        # 8 weeks x 2 destinations x 2 airports x 2.
        "google_round": 64,
        "google_hours": 24,
        "google_day": 64,
        "google_minutes": 27,
        "ryanair_round": 16,
        "ryanair_hours": 3,
        "high": False,
        "too_many": False,
        "limit": 300,
        # No other search: the total is this one.
        "other_day": 0,
        "total_day": 64,
        "too_many_total": False,
    }


# 8 weeks x 5 destinations x 2 airports x 2 = 160 Google requests a day.
GOOGLE_160 = {"sources": ["google"], "destinations": ["LIS", "PAR", "LON", "AMS", "BCN"], "weeks": 8}


async def test_google_limit_counts_every_search(
    aiohttp_client: Any, client: TestClient, tmp_path: Path, session: aiohttp.ClientSession, clock: Clock
) -> None:
    """Two searches of 160 a day are 320 from the same connection: the second one is refused."""
    with patch("flight_prices_engine.sources.google.GoogleSource.search", return_value=[]):
        assert (await client.put("/api/searches/first", json=body(**GOOGLE_160))).status == 200
        response = await client.put("/api/searches/second", json=body(**GOOGLE_160))
        assert response.status == 400
        assert (await response.json())["error"] == "google_too_many_total"
        # The form sees it before saving, and the search being changed is not counted twice.
        options = body(**GOOGLE_160)["options"]
        count = await (await client.post("/api/requests", json={"options": options})).json()
        assert (count["google_day"], count["other_day"], count["total_day"]) == (160, 160, 320)
        assert count["too_many_total"] is True and count["high"] is True
        count = await (await client.post("/api/requests", json={"options": options, "search_id": "first"})).json()
        assert (count["total_day"], count["too_many_total"]) == (160, False)
        # Fewer requests always pass, even over the limit.
        fewer = body(**{**GOOGLE_160, "destinations": ["LIS"]})
        assert (await client.put("/api/searches/second", json=fewer)).status == 200
        info = await (await client.get("/api/info")).json()
        assert info["google"]["day"] == 192
        await client.app[ENGINE].close()

        # After a restart the saved searches count before their client sends them again,
        # and a search sent again as it was is never refused.
        restarted = await aiohttp_client(create_app(await _engine(tmp_path, session, clock)))
        assert (await (await restarted.get("/api/info")).json())["google"]["day"] == 192
        assert (await restarted.put("/api/searches/first", json=body(**GOOGLE_160))).status == 200
        await restarted.app[ENGINE].close()


async def _engine(tmp_path: Path, session: aiohttp.ClientSession, clock: Clock) -> Engine:
    engine = Engine(Store(tmp_path), session, clock)
    await engine.load()
    return engine


async def test_google_requests_of_the_last_day(client: TestClient, clock: Clock) -> None:
    with patch("flight_prices_engine.sources.google.GoogleSource.search", return_value=[]):
        await client.put("/api/searches/entry1", json=body(sources=["google"], destinations=["LIS"]))
        search = client.app[ENGINE].searches["entry1"]
        for _ in range(500):
            if search.states["google"].last_success:
                break
            await asyncio.sleep(0.01)
    # Two airports, two weeks: the outbound found nothing, so no return was searched.
    assert (await (await client.get("/api/info")).json())["google"]["last_24h"] == 4
    clock.tick(timedelta(hours=24, minutes=1))
    assert (await (await client.get("/api/info")).json())["google"]["last_24h"] == 0


async def test_list_and_title(client: TestClient) -> None:
    await client.put("/api/searches/b", json={**body(), "title": "Weekend from Milan"})
    await client.put("/api/searches/a", json={**body(origins=["TRN"]), "title": "Another"})
    assert await (await client.get("/api/searches")).json() == [
        {"id": "a", "title": "Another", "running": True, "google_day": 0},
        {"id": "b", "title": "Weekend from Milan", "running": True, "google_day": 0},
    ]
    # Renaming searches nothing again.
    search = client.app[ENGINE].searches["b"]
    await client.put("/api/searches/b", json={**body(), "title": "Renamed"})
    assert client.app[ENGINE].searches["b"] is search
    assert (await (await client.get("/api/searches/b")).json())["title"] == "Renamed"


async def test_page(client: TestClient) -> None:
    response = await client.get("/")
    assert response.status == 200
    assert response.content_type == "text/html"
    page = await response.text()
    assert "<title>Flight Prices</title>" in page
    # Relative addresses: the page also works behind Home Assistant's ingress.
    assert "fetch(`api/${path}`" in page


@pytest.fixture
async def locked(
    aiohttp_client: Any, tmp_path: Path, session: aiohttp.ClientSession, clock: Clock
) -> AsyncGenerator[TestClient]:
    yield await aiohttp_client(create_app(Engine(Store(tmp_path), session, clock), password="s3cret"))


@pytest.mark.parametrize("path", ["/", "/api/info", "/api/searches"])
async def test_password(locked: TestClient, path: str) -> None:
    response = await locked.get(path)
    assert response.status == 401
    assert response.headers["WWW-Authenticate"].startswith("Basic")
    assert (await locked.get(path, headers={"Authorization": "Bearer wrong"})).status == 401
    # The integration's token, and the browser's login with any user name.
    assert (await locked.get(path, headers={"Authorization": "Bearer s3cret"})).status == 200
    basic = base64.b64encode(b"me:s3cret").decode()
    assert (await locked.get(path, headers={"Authorization": f"Basic {basic}"})).status == 200
    assert (await locked.get(path, headers={"Authorization": "Basic !!"})).status == 401


async def test_ingress_needs_no_password(
    aiohttp_client: Any, tmp_path: Path, session: aiohttp.ClientSession, clock: Clock
) -> None:
    app = create_app(Engine(Store(tmp_path), session, clock), password="s3cret", trusted="127.0.0.1")
    client = await aiohttp_client(app)
    assert (await client.get("/api/info")).status == 200
