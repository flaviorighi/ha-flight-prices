"""Repairs for the Flight Prices integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from . import ISSUE_APP_MISSING, connect_entries
from .api import connection
from .config_flow import APP_SCHEMA, check_app
from .const import APP_URL, CONF_URL, DEFAULT_URL


class AppMissingFlow(RepairsFlow):
    """The searches of version 0 need the app: where it is, when Home Assistant did not find it."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        # Repairs start the flow with the issue's id, not with what the form asks.
        return await self.async_step_app()

    async def async_step_app(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            app = connection(user_input)
            if not (errors := await check_app(self.hass, app)):
                connect_entries(self.hass, app)
                return self.async_create_entry(data={})
        return self.async_show_form(
            step_id="app",
            data_schema=self.add_suggested_values_to_schema(APP_SCHEMA, user_input or {CONF_URL: DEFAULT_URL}),
            errors=errors,
            description_placeholders={"app_url": APP_URL},
        )


async def async_create_fix_flow(hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None) -> RepairsFlow:
    assert issue_id == ISSUE_APP_MISSING
    return AppMissingFlow()
