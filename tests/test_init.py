"""Tests for the setup, the coordinator and the sensors: the app is faked."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock

import aiohttp
from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.flight_prices import ISSUE_APP_MISSING
from custom_components.flight_prices.const import DOMAIN
from homeassistant.components.repairs import DOMAIN as REPAIRS_DOMAIN, repairs_flow_manager
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, issue_registry as ir
from homeassistant.setup import async_setup_component

from .conftest import APP, FakeApp, make_entry, result, source_state, trip

NOW = "2026-11-04 10:00:00+00:00"


@pytest.fixture(autouse=True)
def frozen(freezer: FrozenDateTimeFactory) -> FrozenDateTimeFactory:
    freezer.move_to(NOW)
    return freezer


async def _setup(hass: HomeAssistant, entry: MockConfigEntry | None = None, **options: Any) -> MockConfigEntry:
    entry = entry or make_entry(**options)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_sensors(hass: HomeAssistant, app: FakeApp) -> None:
    hass.config.currency = "EUR"
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.LOADED

    # The search, as the app takes it: the options with the currency, language and time zone of the home.
    sent = app.searches[entry.entry_id]
    assert sent["options"] == dict(entry.options)
    assert (sent["currency"], sent["language"], sent["time_zone"]) == ("EUR", "en", hass.config.time_zone)
    # The name, for the app's page.
    assert sent["title"] == "Weekend"
    assert "restore" not in sent

    week = hass.states.get("sensor.weekend_week_1")
    assert float(week.state) == 131.98
    assert week.attributes["unit_of_measurement"] == "EUR"
    assert week.attributes["outbound_date"] == "2026-11-06"
    assert week.attributes["return_date"] == "2026-11-08"
    assert week.attributes["origins"] == ["MXP", "BGY"]
    assert week.attributes["outbound_hours"] == [19, 24]
    assert week.attributes["return_hours"] == [14, 24]
    assert week.attributes["destinations_found"] == 3
    first = week.attributes["trips"][0]
    assert first["city"] == "Varsavia"
    assert first["return"]["flights"] == "FR1904"

    assert hass.states.get("sensor.weekend_week_2").state == "unknown"
    cheapest = hass.states.get("sensor.weekend_cheapest_trip")
    assert float(cheapest.state) == 131.98
    assert cheapest.attributes["city"] == "Varsavia"
    assert cheapest.attributes["outbound_date"] == "2026-11-06"
    search = hass.states.get("sensor.weekend_ryanair_search")
    assert search.state == "2026-11-04T10:00:00+00:00"
    assert search.attributes["error"] is None
    assert search.attributes["trips"] == 3


async def test_destination_and_google_sensors(hass: HomeAssistant, app: FakeApp) -> None:
    app.answer = result(ryanair=source_state(), google={**source_state(), "running": True})
    app.answer["weeks"][0]["trips"].insert(0, trip("LIS", "Lisbona", "PT", 110, "MXP", "google"))
    await _setup(hass, sources=["ryanair", "google"], google_destinations=["LIS"])
    lisbon = hass.states.get("sensor.weekend_lis")
    assert float(lisbon.state) == 110
    assert lisbon.attributes["city"] == "Lisbona"
    assert lisbon.attributes["weeks"] == [
        {
            "outbound_date": "2026-11-06",
            "return_date": "2026-11-08",
            "price": 110,
            "airline": "Ryanair",
            "source": "google",
        }
    ]
    assert hass.states.get("sensor.weekend_google_flights_search").attributes["running"] is True


async def test_results_of_version_0_move_to_the_app(
    hass: HomeAssistant, app: FakeApp, hass_storage: dict[str, Any]
) -> None:
    entry = make_entry()
    saved = {"sources": {"ryanair": {"fingerprint": "x", "trips": []}}, "names": {}}
    hass_storage[f"{DOMAIN}.{entry.entry_id}"] = {"version": 1, "key": f"{DOMAIN}.{entry.entry_id}", "data": saved}
    await _setup(hass, entry)
    assert app.searches[entry.entry_id]["restore"] == saved
    # Sent once: the next start sends the search alone.
    assert f"{DOMAIN}.{entry.entry_id}" not in hass_storage
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert "restore" not in app.puts[-1]


async def test_app_restarted(hass: HomeAssistant, app: FakeApp, frozen: FrozenDateTimeFactory) -> None:
    entry = await _setup(hass)
    assert len(app.puts) == 1
    # The app restarted and does not run the search until it gets it again.
    app.searches.clear()
    frozen.tick(timedelta(minutes=1, seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(app.puts) == 2
    assert entry.entry_id in app.searches
    assert float(hass.states.get("sensor.weekend_week_1").state) == 131.98


async def test_app_offline(hass: HomeAssistant, app: FakeApp, frozen: FrozenDateTimeFactory) -> None:
    app.online = False
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.SETUP_RETRY

    app.online = True
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    # Stopped later: the sensors are unavailable until it answers again.
    app.online = False
    frozen.tick(timedelta(minutes=1, seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.weekend_week_1").state == "unavailable"


async def test_search_refused(hass: HomeAssistant, app: FakeApp) -> None:
    app.refuse = "google_too_many"
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.SETUP_ERROR


async def test_every_source_failing(hass: HomeAssistant, app: FakeApp, frozen: FrozenDateTimeFactory) -> None:
    await _setup(hass)
    app.answer = result(ryanair=source_state(last_success=None, error="HTTP 500"))
    app.answer["weeks"][0]["trips"] = []
    frozen.tick(timedelta(minutes=1, seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.weekend_week_1").state == "unavailable"


async def test_version_1_without_app(hass: HomeAssistant, app: FakeApp) -> None:
    """A search of version 0 waits for the app; the repair asks where it is and connects it."""
    assert await async_setup_component(hass, REPAIRS_DOMAIN, {})
    entry = await _setup(hass, make_entry(version=1, url=None))
    assert entry.version == 2
    assert entry.state is ConfigEntryState.SETUP_ERROR
    issue = ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_APP_MISSING)
    assert issue is not None and issue.is_fixable

    app.mock.get("http://nowhere.test:1/api/info", exc=aiohttp.ClientConnectionError("refused"))
    flows = repairs_flow_manager(hass)
    flow = await flows.async_init(DOMAIN, data={"issue_id": ISSUE_APP_MISSING})
    assert flow["step_id"] == "app"
    flow = await flows.async_configure(flow["flow_id"], {"url": "http://nowhere.test:1"})
    assert flow["errors"] == {"base": "cannot_connect"}
    flow = await flows.async_configure(flow["flow_id"], {"url": f"{APP}/"})
    assert flow["type"] == "create_entry"
    await hass.async_block_till_done()

    assert entry.data == {"url": APP}
    assert entry.state is ConfigEntryState.LOADED
    assert ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_APP_MISSING) is None


async def test_version_1_with_the_app_known(hass: HomeAssistant, app: FakeApp) -> None:
    await _setup(hass)
    old = make_entry(version=1, url=None, origins=["TRN"])
    await _setup(hass, old)
    # Another search already knows where the app is.
    assert old.data == {"url": APP}
    assert old.state is ConfigEntryState.LOADED


async def test_remove_deletes_the_search(hass: HomeAssistant, app: FakeApp) -> None:
    entry = await _setup(hass)
    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert app.deleted == [entry.entry_id]


async def test_fewer_weeks_remove_entities(hass: HomeAssistant, app: FakeApp) -> None:
    entry = await _setup(hass)
    hass.config_entries.async_update_entry(entry, options={**entry.options, "weeks": 1})
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    assert registry.async_get_entity_id("sensor", "flight_prices", f"{entry.entry_id}_week_2") is None
    assert registry.async_get_entity_id("sensor", "flight_prices", f"{entry.entry_id}_week_1") is not None


async def test_card_is_served(hass: HomeAssistant, app: FakeApp, frontend: MagicMock) -> None:
    await _setup(hass)
    paths = hass.http.async_register_static_paths.call_args.args[0]
    assert [(path.url_path, path.path.endswith("frontend/flight-prices-card.js")) for path in paths] == [
        ("/flight_prices/flight-prices-card.js", True)
    ]
    # Loaded on every dashboard, with the file's hash in the address for the browsers' cache.
    url = frontend.call_args.args[1]
    assert url.startswith("/flight_prices/flight-prices-card.js?v=")
    assert len(url.split("v=")[1]) == 8


async def test_removing_the_search_without_app_removes_the_repair(hass: HomeAssistant, app: FakeApp) -> None:
    entry = await _setup(hass, make_entry(version=1, url=None))
    assert ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_APP_MISSING) is not None
    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_APP_MISSING) is None
    assert app.deleted == []


async def test_app_with_a_password(hass: HomeAssistant, app: FakeApp, frozen: FrozenDateTimeFactory) -> None:
    app.password = "s3cret"
    entry = await _setup(hass, make_entry(password="s3cret"))
    assert entry.state is ConfigEntryState.LOADED
    # The password changed in the app: the sensors become unavailable until Reconfigure.
    app.password = "other"
    frozen.tick(timedelta(minutes=1, seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.weekend_week_1").state == "unavailable"
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
