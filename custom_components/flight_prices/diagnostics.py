"""Diagnostics for the Flight Prices integration."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .api import AppError
from .coordinator import FlightPricesConfigEntry


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: FlightPricesConfigEntry) -> dict[str, Any]:
    """The search, the app, the state of each source and how many trips each week has. Nothing personal is stored."""
    coordinator = entry.runtime_data
    data = coordinator.data
    try:
        app: dict[str, Any] = await coordinator.app.info()
    except AppError as err:
        app = {"error": str(err)}
    return {
        "options": dict(entry.options),
        "app": {"url": coordinator.app.url, **{key: app.get(key) for key in ("version", "api", "error")}},
        "sources": data["sources"],
        "weeks": [
            {
                "outbound": week["outbound_date"],
                "inbound": week["return_date"],
                "trips": len(week["trips"]),
                "cheapest": week["trips"][0]["price"] if week["trips"] else None,
            }
            for week in data["weeks"]
        ],
    }
