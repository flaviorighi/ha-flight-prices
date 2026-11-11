"""Coordinator for the Flight Prices integration: the search runs in the app, this reads what it found."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import AppError, CannotConnect, FlightPricesApp
from .const import (
    CONF_DESTINATIONS,
    CONF_GOOGLE_DESTINATIONS,
    CONF_ORIGINS,
    CONF_OUTBOUND_FROM,
    CONF_OUTBOUND_TO,
    CONF_RETURN_FROM,
    CONF_RETURN_TO,
    CONF_WEEKS,
    DEFAULT_OUTBOUND_FROM,
    DEFAULT_OUTBOUND_TO,
    DEFAULT_RETURN_FROM,
    DEFAULT_RETURN_TO,
    DEFAULT_WEEKS,
    DOMAIN,
    LEGACY_STORAGE_VERSION,
    UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

type FlightPricesConfigEntry = ConfigEntry[FlightPricesCoordinator]


def legacy_store(hass: HomeAssistant, entry_id: str) -> Store[dict[str, Any]]:
    """Where version 0 kept what the sources found, before the app existed."""
    return Store(hass, LEGACY_STORAGE_VERSION, f"{DOMAIN}.{entry_id}")


class FlightPricesCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Sends the search to the app and reads what it found."""

    config_entry: FlightPricesConfigEntry

    def __init__(self, hass: HomeAssistant, entry: FlightPricesConfigEntry, app: FlightPricesApp) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=UPDATE_INTERVAL)
        self.app = app
        options = entry.options
        self.weeks = int(options.get(CONF_WEEKS, DEFAULT_WEEKS))
        # Every destination of a list, of any source: one sensor each.
        self.destinations = list(
            dict.fromkeys((*options.get(CONF_DESTINATIONS, ()), *options.get(CONF_GOOGLE_DESTINATIONS, ())))
        )
        # What was searched, for dashboards: hours run from..to, 24 being midnight.
        self.search_attributes = {
            "origins": list(options[CONF_ORIGINS]),
            "outbound_hours": [
                int(options.get(CONF_OUTBOUND_FROM, DEFAULT_OUTBOUND_FROM)),
                int(options.get(CONF_OUTBOUND_TO, DEFAULT_OUTBOUND_TO)),
            ],
            "return_hours": [
                int(options.get(CONF_RETURN_FROM, DEFAULT_RETURN_FROM)),
                int(options.get(CONF_RETURN_TO, DEFAULT_RETURN_TO)),
            ],
        }

    @property
    def active_sources(self) -> list[str]:
        return list(self.data.get("sources", {})) if self.data else []

    def _search(self, restore: dict[str, Any] | None = None) -> dict[str, Any]:
        """The search as the app takes it, with the currency, language and time zone of the home."""
        search: dict[str, Any] = {
            "options": dict(self.config_entry.options),
            "currency": self.hass.config.currency,
            "language": self.hass.config.language,
            "time_zone": self.hass.config.time_zone,
        }
        if restore:
            search["restore"] = restore
        return search

    async def _send(self, restore: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            return await self.app.put_search(self.config_entry.entry_id, self._search(restore))
        except CannotConnect as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
                translation_placeholders={"error": str(err)},
            ) from err
        except AppError as err:
            # A search the app refuses, such as one over the Google limit: only a change of the options helps.
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="search_refused",
                translation_placeholders={"error": str(err)},
            ) from err

    async def _async_setup(self) -> None:
        """Send the search once: at every start the app gets it as it is now."""
        store = legacy_store(self.hass, self.config_entry.entry_id)
        # What version 0 had found goes to the app, so moving to it repeats no search.
        restore = await store.async_load()
        await self._send(restore)
        if restore:
            await store.async_remove()
            _LOGGER.info("Moved what %s had found to the app", self.config_entry.title)

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data = await self.app.get_search(self.config_entry.entry_id)
        except CannotConnect as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
                translation_placeholders={"error": str(err)},
            ) from err
        if data is None:
            # The app restarted: it searches again only what is due, from what it saved.
            data = await self._send()
        sources = data.get("sources", {}).values()
        if (
            sources
            and not any(week["trips"] for week in data["weeks"])
            and all(state["error"] and not state["last_success"] for state in sources)
        ):
            # Nothing found ever and every source failed.
            errors = "; ".join(f"{name}: {state['error']}" for name, state in data["sources"].items())
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="update_failed", translation_placeholders={"error": errors}
            )
        return data


def parse_time(value: str | None) -> datetime | None:
    return dt_util.parse_datetime(value) if value else None
