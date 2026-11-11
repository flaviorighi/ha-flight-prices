"""Tests for the config flow."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import aiohttp
import pytest

from custom_components.flight_prices.const import DOMAIN
from homeassistant.config_entries import SOURCE_HASSIO, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from homeassistant.helpers.service_info.hassio import HassioServiceInfo

from .conftest import APP, OPTIONS, FakeApp, make_entry

FORM = {
    "name": " Weekend ",
    "origins": ["mxp", " BGY", "MXP"],
    "sources": ["ryanair"],
    "weeks": 8,
    "outbound_day": "4",
    "outbound_from": 19,
    "outbound_to": 24,
    "return_day": "6",
    "return_from": 14,
    "return_to": 24,
    "direct_only": True,
}


@pytest.fixture(autouse=True)
def no_setup():
    with patch("custom_components.flight_prices.async_setup_entry", return_value=True):
        yield


@pytest.fixture(autouse=True)
def running_app(app: FakeApp) -> FakeApp:
    """Every form talks to the app: it counts the requests."""
    return app


async def _start(hass: HomeAssistant) -> dict[str, Any]:
    """The search form: the first search asks where the app is, the next ones know it."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    if result["step_id"] == "app":
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": APP})
    assert result["step_id"] == "user"
    return result


async def test_app_address(hass: HomeAssistant, app: FakeApp) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["step_id"] == "app"
    app.mock.get("http://other.test:8765/api/info", exc=aiohttp.ClientConnectionError("refused"))
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": "http://other.test:8765"})
    assert result["errors"] == {"base": "cannot_connect"}
    app.api = 2
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": APP})
    assert result["errors"] == {"base": "incompatible"}
    app.api = 1
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": f" {APP}/ "})
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], FORM)
    assert result["data"] == {"url": APP}


async def test_discovery_offers_a_first_search(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_HASSIO}, data=_discovery())
    assert result["step_id"] == "hassio_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], FORM)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"url": APP}
    # More searches can be added: the entry took no id from the discovery.
    assert result["result"].unique_id is None


async def test_discovery_connects_the_searches_of_version_0(hass: HomeAssistant) -> None:
    old = make_entry(url=None)
    old.add_to_hass(hass)
    with patch("homeassistant.config_entries.ConfigEntries.async_schedule_reload") as reload:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_HASSIO}, data=_discovery())
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "app_connected"
    assert old.data == {"url": APP}
    reload.assert_called_once_with(old.entry_id)


async def test_discovery_with_searches_connected(hass: HomeAssistant) -> None:
    make_entry().add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_HASSIO}, data=_discovery())
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_discovery_of_an_app_that_does_not_answer(hass: HomeAssistant, app: FakeApp) -> None:
    app.online = False
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_HASSIO}, data=_discovery())
    assert result["reason"] == "cannot_connect"


async def test_reconfigure_moves_every_search(hass: HomeAssistant, app: FakeApp) -> None:
    first, second = make_entry(url="http://old.test:8765"), make_entry(url="http://old.test:8765", origins=["TRN"])
    other = make_entry(url="http://elsewhere.test:8765", origins=["VCE"])
    for entry in (first, second, other):
        entry.add_to_hass(hass)
    result = await first.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": APP})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert (first.data, second.data, other.data) == ({"url": APP}, {"url": APP}, {"url": "http://elsewhere.test:8765"})


async def test_options_with_the_app_stopped(hass: HomeAssistant, app: FakeApp) -> None:
    entry = make_entry()
    entry.add_to_hass(hass)
    app.online = False
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["errors"] == {"base": "cannot_connect"}
    assert result["description_placeholders"]["google_day"] == "…"


def _discovery() -> HassioServiceInfo:
    return HassioServiceInfo(
        config={"host": "flight-prices.test", "port": 8765},
        name="Flight Prices",
        slug="a0d7b954_flight_prices",
        uuid="1234",
    )


async def test_create_anywhere(hass: HomeAssistant) -> None:
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], FORM)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Weekend"
    assert result["data"] == {"url": APP}
    assert result["options"] == {**OPTIONS, "weeks": 8}


@pytest.mark.parametrize(
    ("changes", "errors"),
    [
        ({"origins": []}, {"origins": "no_origin"}),
        ({"origins": ["MALPENSA"]}, {"origins": "invalid_code"}),
        ({"destinations": ["LIS", "12"]}, {"destinations": "invalid_code"}),
        ({"sources": []}, {"sources": "no_source"}),
        ({"exclude_countries": ["ITA"]}, {"exclude_countries": "invalid_country"}),
        ({"google_origins": ["MALPENSA"]}, {"google_origins": "invalid_code"}),
        ({"sources": ["google"]}, {"google_destinations": "google_needs_destinations"}),
        ({"sources": ["ryanair", "google"]}, {"google_destinations": "google_needs_destinations"}),
        ({"google_destinations": ["PARIS"]}, {"google_destinations": "invalid_code"}),
        ({"outbound_from": 20, "outbound_to": 19}, {"outbound_to": "invalid_hours"}),
        ({"return_from": 14, "return_to": 14}, {"return_to": "invalid_hours"}),
        # 12 weeks x 7 destinations x 2 airports x 2 = 336 Google requests a day, over 300.
        (
            {
                "sources": ["google"],
                "weeks": 12,
                "google_destinations": ["LIS", "PAR", "LON", "AMS", "BCN", "OPO", "BUD"],
            },
            {"google_destinations": "google_too_many"},
        ),
    ],
)
async def test_errors(hass: HomeAssistant, changes: dict[str, Any], errors: dict[str, str]) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {**FORM, **changes})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == errors


async def test_google_requests_in_the_error(hass: HomeAssistant) -> None:
    result = await _start(hass)
    # The guide is linked before anything is filled in.
    assert result["description_placeholders"]["guide_url"].endswith("docs/configuration.md")
    destinations = ["LIS", "PAR", "LON", "AMS", "BCN", "OPO", "BUD"]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**FORM, "sources": ["google"], "weeks": 12, "google_destinations": destinations}
    )
    assert result["description_placeholders"]["count"] == "336"
    assert result["description_placeholders"]["limit"] == "300"
    # One airport for Google halves it: 168 a day.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {**FORM, "sources": ["google"], "weeks": 12, "google_destinations": destinations, "google_origins": ["MXP"]},
    )
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "summary"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "save"})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_google_with_destinations(hass: HomeAssistant) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**FORM, "sources": ["google"], "destinations": ["lis", "LON"]}
    )
    # 8 weeks x 2 destinations x 2 airports x 2 = 64 a round, once a day.
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["save", "change"]
    placeholders = result["description_placeholders"]
    assert (placeholders["google_round"], placeholders["google_day"], placeholders["google_hours"]) == (
        "64",
        "64",
        "24",
    )
    assert placeholders["google_minutes"] == "27"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "save"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"]["destinations"] == ["LIS", "LON"]


async def test_summary_warns_close_to_the_limit_and_goes_back(hass: HomeAssistant) -> None:
    result = await _start(hass)
    # 8 weeks x 7 destinations x 2 airports x 2 = 224 a day: allowed, but close to the limit.
    destinations = ["LIS", "PAR", "LON", "AMS", "BCN", "OPO", "BUD"]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**FORM, "sources": ["ryanair", "google"], "google_destinations": destinations}
    )
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "summary_high"
    assert result["description_placeholders"]["google_day"] == "224"
    # Change the search: the form comes back as it was filled in.
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "change"})
    assert result["type"] is FlowResultType.FORM
    schema = {str(key): key.description for key in result["data_schema"].schema}
    assert schema["google_destinations"]["suggested_value"] == destinations
    assert schema["name"]["suggested_value"] == "Weekend"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**FORM, "sources": ["ryanair", "google"], "google_destinations": ["LIS"]}
    )
    assert result["step_id"] == "summary"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "save"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"]["google_destinations"] == ["LIS"]


async def test_exclude_countries(hass: HomeAssistant) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {**FORM, "exclude_countries": ["it"]})
    assert result["options"]["exclude_countries"] == ["IT"]


async def test_same_search_twice(hass: HomeAssistant) -> None:
    make_entry().add_to_hass(hass)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], FORM)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options(hass: HomeAssistant) -> None:
    entry = make_entry()
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    form = {key: value for key, value in FORM.items() if key != "name"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**form, "destinations": ["PMO"], "ryanair_interval": 6, "google_interval": 24}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["destinations"] == ["PMO"]
    assert entry.options["ryanair_interval"] == 6


async def test_options_google_limits(hass: HomeAssistant) -> None:
    entry = make_entry()
    entry.add_to_hass(hass)
    form = {key: value for key, value in FORM.items() if key != "name"}
    google = {"sources": ["ryanair", "google"], "ryanair_interval": 3}
    result = await hass.config_entries.options.async_init(entry.entry_id)
    # Every 6 hours is too often, whatever the requests: the field does not accept it.
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            result["flow_id"], {**form, **google, "google_destinations": ["LIS"], "google_interval": 6}
        )
    # 8 weeks x 5 destinations x 2 airports x 2 = 160 a round: twice a day is 320, over 300.
    destinations = ["LIS", "PAR", "LON", "AMS", "BCN"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**form, **google, "google_destinations": destinations, "google_interval": 12}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"google_destinations": "google_too_many"}
    assert result["description_placeholders"]["count"] == "320"
    # Once a day the same search is 160 requests: accepted, after the summary.
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**form, **google, "google_destinations": destinations, "google_interval": 24}
    )
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "summary"
    assert result["description_placeholders"]["google_day"] == "160"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "save"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["google_destinations"] == destinations


async def test_configure_shows_the_requests_of_the_saved_search(hass: HomeAssistant) -> None:
    entry = make_entry(sources=["ryanair", "google"], google_destinations=["LIS", "PAR"], google_origins=["MXP"])
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    # 2 weeks x 2 destinations x 1 airport x 2 = 8 a day.
    assert result["description_placeholders"]["google_day"] == "8"
