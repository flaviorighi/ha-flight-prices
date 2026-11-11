"""Tests for the HTTP API."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

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
    assert await response.json() == {"version": __version__, "api": 1, "searches": []}


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
    }
