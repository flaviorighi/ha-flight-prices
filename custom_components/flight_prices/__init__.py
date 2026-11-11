"""The Flight Prices integration."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import config_validation as cv, issue_registry as ir
from homeassistant.helpers.typing import ConfigType

from .api import AppError, app_client, connection
from .const import APP_URL, CONF_PASSWORD, CONF_URL, DOMAIN
from .coordinator import FlightPricesConfigEntry, FlightPricesCoordinator, legacy_store

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# The dashboard card, served by the integration and loaded on every dashboard.
CARD_FILE = Path(__file__).parent / "frontend" / "flight-prices-card.js"
CARD_URL = f"/{DOMAIN}/flight-prices-card.js"
# Raised for the searches of version 0 while the app is missing; the repair asks where it is.
ISSUE_APP_MISSING = "app_missing"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the card: it shows up in the card picker with nothing to add by hand."""
    content = await hass.async_add_executor_job(CARD_FILE.read_bytes)
    await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, str(CARD_FILE), cache_headers=True)])
    # A new file gets a new address, so browsers do not keep the old one in cache.
    add_extra_js_url(hass, f"{CARD_URL}?v={hashlib.sha256(content).hexdigest()[:8]}")
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Version 1 searched by itself; from version 2 the app searches, at an address the entry keeps."""
    if entry.version > 2:
        return False
    if entry.version == 1:
        # Another search already connected tells where the app is; otherwise the repair or discovery will.
        app = known_app(hass)
        hass.config_entries.async_update_entry(entry, data={**entry.data, **(app or {})}, version=2)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: FlightPricesConfigEntry) -> bool:
    """Set up a search: the app runs it, the sensors show what it found."""
    if CONF_URL not in entry.data:
        ir.async_create_issue(
            hass,
            DOMAIN,
            ISSUE_APP_MISSING,
            is_fixable=True,
            is_persistent=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key=ISSUE_APP_MISSING,
            translation_placeholders={"app_url": APP_URL},
            learn_more_url=APP_URL,
        )
        raise ConfigEntryError(translation_domain=DOMAIN, translation_key="app_missing")
    app = app_client(hass, entry.data)
    coordinator = FlightPricesCoordinator(hass, entry, app)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FlightPricesConfigEntry) -> bool:
    """Unload a search; the app goes on searching it until it is deleted."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete the search from the app, and anything version 0 had left behind."""
    await legacy_store(hass, entry.entry_id).async_remove()
    if CONF_URL not in entry.data:
        if not entries_without_app(hass):
            ir.async_delete_issue(hass, DOMAIN, ISSUE_APP_MISSING)
        return
    try:
        await app_client(hass, entry.data).delete_search(entry.entry_id)
    except AppError as err:
        # Left in the app's data folder, it does not search: only a search sent again runs.
        _LOGGER.warning("Could not delete the search %s from the app: %s", entry.title, err)


def entries_without_app(hass: HomeAssistant) -> list[ConfigEntry]:
    return [entry for entry in hass.config_entries.async_entries(DOMAIN) if CONF_URL not in entry.data]


def known_app(hass: HomeAssistant) -> dict[str, Any] | None:
    """The app the other searches use: one app runs every search."""
    return next(
        (connection(entry.data) for entry in hass.config_entries.async_entries(DOMAIN) if CONF_URL in entry.data),
        None,
    )


def connect_entries(hass: HomeAssistant, app: dict[str, Any]) -> int:
    """Give the app to the searches that lack it, or a new password to those at its address; set them up again."""
    changed = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if CONF_URL not in entry.data
        or (entry.data[CONF_URL] == app[CONF_URL] and entry.data.get(CONF_PASSWORD) != app.get(CONF_PASSWORD))
    ]
    for entry in changed:
        data = {key: value for key, value in entry.data.items() if key != CONF_PASSWORD}
        hass.config_entries.async_update_entry(entry, data={**data, **app})
        hass.config_entries.async_schedule_reload(entry.entry_id)
    if not entries_without_app(hass):
        ir.async_delete_issue(hass, DOMAIN, ISSUE_APP_MISSING)
    return len(changed)
