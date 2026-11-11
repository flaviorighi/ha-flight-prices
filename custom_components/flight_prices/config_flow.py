"""Config flow for the Flight Prices integration."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.helpers.service_info.hassio import HassioServiceInfo

from . import connect_entries, known_app
from .api import AppError, FlightPricesApp, Incompatible, app_client, connection
from .const import (
    APP_URL,
    CONF_DESTINATIONS,
    CONF_DIRECT_ONLY,
    CONF_EXCLUDE_COUNTRIES,
    CONF_GOOGLE_DESTINATIONS,
    CONF_GOOGLE_INTERVAL,
    CONF_GOOGLE_ORIGINS,
    CONF_ORIGINS,
    CONF_OUTBOUND_DAY,
    CONF_OUTBOUND_FROM,
    CONF_OUTBOUND_TO,
    CONF_PASSWORD,
    CONF_RETURN_DAY,
    CONF_RETURN_FROM,
    CONF_RETURN_TO,
    CONF_RYANAIR_INTERVAL,
    CONF_SOURCES,
    CONF_URL,
    CONF_WEEKS,
    DEFAULT_DIRECT_ONLY,
    DEFAULT_GOOGLE_HOURS,
    DEFAULT_OUTBOUND_DAY,
    DEFAULT_OUTBOUND_FROM,
    DEFAULT_OUTBOUND_TO,
    DEFAULT_RETURN_DAY,
    DEFAULT_RETURN_FROM,
    DEFAULT_RETURN_TO,
    DEFAULT_RYANAIR_HOURS,
    DEFAULT_URL,
    DEFAULT_WEEKS,
    DOMAIN,
    GOOGLE_MIN_HOURS,
    GUIDE_URL,
    MAX_WEEKS,
    SOURCE_GOOGLE,
    SOURCE_RYANAIR,
    SOURCES,
)
from .coordinator import FlightPricesConfigEntry

AIRPORT_RE = re.compile(r"^[A-Z]{3}$")
COUNTRY_RE = re.compile(r"^[A-Z]{2}$")

CODES = TextSelector(TextSelectorConfig(multiple=True))
DAY = SelectSelector(
    SelectSelectorConfig(
        options=[str(day) for day in range(7)], translation_key="weekday", mode=SelectSelectorMode.DROPDOWN
    )
)


def _number(low: int, high: int, unit: str | None = None) -> NumberSelector:
    config = NumberSelectorConfig(min=low, max=high, step=1, mode=NumberSelectorMode.BOX)
    if unit:
        config["unit_of_measurement"] = unit
    return NumberSelector(config)


SEARCH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ORIGINS): CODES,
        vol.Optional(CONF_DESTINATIONS): CODES,
        vol.Optional(CONF_EXCLUDE_COUNTRIES): CODES,
        vol.Required(CONF_SOURCES, default=[SOURCE_RYANAIR]): SelectSelector(
            SelectSelectorConfig(
                options=list(SOURCES), multiple=True, translation_key="sources", mode=SelectSelectorMode.LIST
            )
        ),
        vol.Optional(CONF_GOOGLE_ORIGINS): CODES,
        vol.Optional(CONF_GOOGLE_DESTINATIONS): CODES,
        vol.Required(CONF_WEEKS, default=DEFAULT_WEEKS): _number(1, MAX_WEEKS),
        vol.Required(CONF_OUTBOUND_DAY, default=str(DEFAULT_OUTBOUND_DAY)): DAY,
        vol.Required(CONF_OUTBOUND_FROM, default=DEFAULT_OUTBOUND_FROM): _number(0, 23, "h"),
        vol.Required(CONF_OUTBOUND_TO, default=DEFAULT_OUTBOUND_TO): _number(1, 24, "h"),
        vol.Required(CONF_RETURN_DAY, default=str(DEFAULT_RETURN_DAY)): DAY,
        vol.Required(CONF_RETURN_FROM, default=DEFAULT_RETURN_FROM): _number(0, 23, "h"),
        vol.Required(CONF_RETURN_TO, default=DEFAULT_RETURN_TO): _number(1, 24, "h"),
        vol.Required(CONF_DIRECT_ONLY, default=DEFAULT_DIRECT_ONLY): BooleanSelector(),
    }
)
APP_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
        vol.Optional(CONF_PASSWORD): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
    }
)
USER_SCHEMA = vol.Schema({vol.Required(CONF_NAME): TextSelector()}).extend(SEARCH_SCHEMA.schema)
OPTIONS_SCHEMA = SEARCH_SCHEMA.extend(
    {
        vol.Required(CONF_RYANAIR_INTERVAL, default=DEFAULT_RYANAIR_HOURS): _number(1, 24, "h"),
        vol.Required(CONF_GOOGLE_INTERVAL, default=DEFAULT_GOOGLE_HOURS): _number(GOOGLE_MIN_HOURS, 168, "h"),
    }
)


def _codes(values: Any) -> list[str]:
    """MXP, " bgy " and duplicates become ["MXP", "BGY"]."""
    if isinstance(values, str):
        values = re.split(r"[\s,;]+", values)
    return list(dict.fromkeys(code.strip().upper() for code in values or () if code.strip()))


async def count(
    app: FlightPricesApp, options: Mapping[str, Any], search_id: str | None = None
) -> tuple[dict[str, Any] | None, dict[str, str]]:
    """What the app counts for these options, with its other searches, and the errors to show."""
    try:
        requests = await app.count_requests(dict(options), search_id)
    except AppError as err:
        return None, {"base": "invalid_auth" if err.code == "invalid_auth" else "cannot_connect"}
    # Many requests from one address get it a captcha from Google, for the whole home.
    if requests["too_many"]:
        return requests, {CONF_GOOGLE_DESTINATIONS: "google_too_many"}
    if requests.get("too_many_total"):
        return requests, {CONF_GOOGLE_DESTINATIONS: "google_too_many_total"}
    return requests, {}


def placeholders(requests: Mapping[str, Any] | None) -> dict[str, str]:
    """For the texts of the forms: the guide, the limit and what the search makes."""
    values = {"guide_url": GUIDE_URL, "app_url": APP_URL}
    keys = ("limit", "google_round", "google_day", "google_minutes", "google_hours", "ryanair_round", "ryanair_hours")
    # Without an answer from the app the numbers are unknown; an error says why.
    values |= {key: str(requests[key]) if requests else "…" for key in keys}
    values["count"] = values["google_day"]
    # This search with the app's others: they all come from the same connection.
    values["total"] = str(requests.get("total_day", requests["google_day"])) if requests else "…"
    return values


def validate(user_input: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """The options to store, and the errors to show; the app counts the requests."""
    errors: dict[str, str] = {}
    origins = _codes(user_input.get(CONF_ORIGINS))
    destinations = _codes(user_input.get(CONF_DESTINATIONS))
    countries = _codes(user_input.get(CONF_EXCLUDE_COUNTRIES))
    google_origins = _codes(user_input.get(CONF_GOOGLE_ORIGINS))
    google_destinations = _codes(user_input.get(CONF_GOOGLE_DESTINATIONS))
    sources = [source for source in SOURCES if source in user_input.get(CONF_SOURCES, ())]
    if not origins:
        errors[CONF_ORIGINS] = "no_origin"
    elif not all(AIRPORT_RE.match(code) for code in origins):
        errors[CONF_ORIGINS] = "invalid_code"
    if not all(AIRPORT_RE.match(code) for code in destinations):
        errors[CONF_DESTINATIONS] = "invalid_code"
    if not all(AIRPORT_RE.match(code) for code in google_origins):
        errors[CONF_GOOGLE_ORIGINS] = "invalid_code"
    if not all(AIRPORT_RE.match(code) for code in google_destinations):
        errors[CONF_GOOGLE_DESTINATIONS] = "invalid_code"
    if not all(COUNTRY_RE.match(code) for code in countries):
        errors[CONF_EXCLUDE_COUNTRIES] = "invalid_country"
    if not sources:
        errors[CONF_SOURCES] = "no_source"
    elif SOURCE_GOOGLE in sources and not (google_destinations or destinations):
        # Google Flights is searched route by route: it cannot look everywhere.
        errors[CONF_GOOGLE_DESTINATIONS] = "google_needs_destinations"
    options: dict[str, Any] = {
        CONF_ORIGINS: origins,
        CONF_DESTINATIONS: destinations,
        CONF_EXCLUDE_COUNTRIES: countries,
        CONF_SOURCES: sources,
        CONF_GOOGLE_ORIGINS: google_origins,
        CONF_GOOGLE_DESTINATIONS: google_destinations,
        CONF_WEEKS: int(user_input[CONF_WEEKS]),
        CONF_OUTBOUND_DAY: int(user_input[CONF_OUTBOUND_DAY]),
        CONF_OUTBOUND_FROM: int(user_input[CONF_OUTBOUND_FROM]),
        CONF_OUTBOUND_TO: int(user_input[CONF_OUTBOUND_TO]),
        CONF_RETURN_DAY: int(user_input[CONF_RETURN_DAY]),
        CONF_RETURN_FROM: int(user_input[CONF_RETURN_FROM]),
        CONF_RETURN_TO: int(user_input[CONF_RETURN_TO]),
        CONF_DIRECT_ONLY: bool(user_input[CONF_DIRECT_ONLY]),
    }
    if options[CONF_OUTBOUND_FROM] >= options[CONF_OUTBOUND_TO]:
        errors[CONF_OUTBOUND_TO] = "invalid_hours"
    if options[CONF_RETURN_FROM] >= options[CONF_RETURN_TO]:
        errors[CONF_RETURN_TO] = "invalid_hours"
    # The interval cannot go under GOOGLE_MIN_HOURS: its field does not accept it.
    for key in (CONF_RYANAIR_INTERVAL, CONF_GOOGLE_INTERVAL):
        if key in user_input:
            options[key] = int(user_input[key])
    return options, errors


def _suggested(options: Mapping[str, Any]) -> dict[str, Any]:
    """Stored options as the form shows them: the days are strings in the selector."""
    values = dict(options)
    for key in (CONF_OUTBOUND_DAY, CONF_RETURN_DAY):
        if key in values:
            values[key] = str(values[key])
    return values


async def check_app(hass: HomeAssistant, app: Mapping[str, Any]) -> dict[str, str]:
    """The errors of an app this integration cannot talk to: wrong address, password or version."""
    try:
        await app_client(hass, app).info()
    except Incompatible:
        return {"base": "incompatible"}
    except AppError as err:
        return {"base": "invalid_auth" if err.code == "invalid_auth" else "cannot_connect"}
    return {}


class FlightPricesConfigFlow(ConfigFlow, domain=DOMAIN):
    """One entry per search: from where, to where, on which days. The app runs them all."""

    VERSION = 2

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: FlightPricesConfigEntry) -> FlightPricesOptionsFlow:
        return FlightPricesOptionsFlow()

    def __init__(self) -> None:
        super().__init__()
        self._name = ""
        self._options: dict[str, Any] = {}
        self._requests: dict[str, Any] | None = None
        # Where the app is, and its password if it has one.
        self._app_data: dict[str, Any] | None = None

    def _app(self) -> FlightPricesApp:
        assert self._app_data is not None
        return app_client(self.hass, self._app_data)

    async def async_step_hassio(self, discovery_info: HassioServiceInfo) -> ConfigFlowResult:
        """The app announced itself: connect the searches waiting for it, or offer a first search."""
        config = discovery_info.config
        app = connection({CONF_URL: f"http://{config['host']}:{config['port']}", CONF_PASSWORD: config.get("password")})
        # One flow for the app, however many times it starts.
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if await check_app(self.hass, app):
            return self.async_abort(reason="cannot_connect")
        # Searches waiting for the app, or a password changed in the app's options.
        if connect_entries(self.hass, app):
            return self.async_abort(reason="app_connected")
        if self.hass.config_entries.async_entries(DOMAIN):
            # Searches already connected, to this app or to another one by choice.
            return self.async_abort(reason="already_configured")
        self._app_data = app
        return await self.async_step_hassio_confirm()

    async def async_step_hassio_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            # The search's entry gets no id: more searches can follow from the add button.
            await self.async_set_unique_id(None)
            return await self.async_step_user()
        return self.async_show_form(step_id="hassio_confirm", description_placeholders={"app_url": APP_URL})

    async def async_step_app(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Where the app is, when Home Assistant did not find it: Docker, or another machine."""
        errors: dict[str, str] = {}
        if user_input is not None:
            app = connection(user_input)
            if not (errors := await check_app(self.hass, app)):
                self._app_data = app
                return await self.async_step_user()
        return self.async_show_form(
            step_id="app",
            data_schema=self.add_suggested_values_to_schema(APP_SCHEMA, user_input or {CONF_URL: DEFAULT_URL}),
            errors=errors,
            description_placeholders={"app_url": APP_URL},
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if self._app_data is None:
            if (app := known_app(self.hass)) is None:
                return await self.async_step_app()
            self._app_data = app
        errors: dict[str, str] = {}
        options: dict[str, Any] = {}
        if user_input is not None:
            options, errors = validate(user_input)
            if not errors:
                requests, errors = await count(self._app(), options)
                if not errors:
                    self._async_abort_entries_match(
                        {
                            key: options[key]
                            for key in (CONF_ORIGINS, CONF_DESTINATIONS, CONF_OUTBOUND_DAY, CONF_RETURN_DAY)
                        }
                    )
                    self._name, self._options, self._requests = user_input[CONF_NAME].strip(), options, requests
                    if requests and requests["google_round"]:
                        return self._summary()
                    return await self.async_step_save()
        requests, count_errors = await count(self._app(), options)
        suggested = user_input or ({CONF_NAME: self._name, **self._options} if self._options else {})
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, _suggested(suggested)),
            errors=errors or {key: value for key, value in count_errors.items() if key == "base"},
            description_placeholders=placeholders(requests),
        )

    def _summary(self) -> ConfigFlowResult:
        """What Google Flights will request, before saving: a form cannot count while it is filled in."""
        assert self._requests is not None
        return self.async_show_menu(
            step_id="summary_high" if self._requests["high"] else "summary",
            menu_options=["save", "change"],
            description_placeholders=placeholders(self._requests),
        )

    async def async_step_summary(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self._summary()

    async def async_step_summary_high(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self._summary()

    async def async_step_save(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._app_data is not None
        return self.async_create_entry(title=self._name, data=self._app_data, options=self._options)

    async def async_step_change(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self.async_step_user()

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Another address for the app; every search that used the old one moves with it."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            app = connection(user_input)
            if not (errors := await check_app(self.hass, app)):
                old = entry.data.get(CONF_URL)
                for other in self.hass.config_entries.async_entries(DOMAIN):
                    if other.entry_id != entry.entry_id and other.data.get(CONF_URL) == old:
                        self.hass.config_entries.async_update_entry(other, data=app)
                        self.hass.config_entries.async_schedule_reload(other.entry_id)
                return self.async_update_reload_and_abort(entry, data=app)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(APP_SCHEMA, user_input or dict(entry.data)),
            errors=errors,
            description_placeholders={"app_url": APP_URL},
        )


class FlightPricesOptionsFlow(OptionsFlowWithReload):
    """Change the search; the entry reloads and the app searches again what changed."""

    def __init__(self) -> None:
        super().__init__()
        self._options: dict[str, Any] = {}
        self._requests: dict[str, Any] | None = None

    def _app(self) -> FlightPricesApp:
        return app_client(self.hass, self.config_entry.data)

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if CONF_URL not in self.config_entry.data:
            return self.async_abort(reason="app_missing", description_placeholders={"app_url": APP_URL})
        errors: dict[str, str] = {}
        if user_input is not None:
            options, errors = validate(user_input)
            if not errors:
                requests, errors = await count(self._app(), options, self.config_entry.entry_id)
                if not errors:
                    self._options, self._requests = options, requests
                    if requests and requests["google_round"]:
                        return self._summary()
                    return await self.async_step_save()
        current = user_input or self._options or self.config_entry.options
        # Opening Configure shows what the saved search makes; after an error, what was sent.
        requests, count_errors = await count(
            self._app(),
            validate(user_input)[0] if user_input else self.config_entry.options,
            self.config_entry.entry_id,
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(OPTIONS_SCHEMA, _suggested(current)),
            errors=errors or {key: value for key, value in count_errors.items() if key == "base"},
            description_placeholders=placeholders(requests),
        )

    def _summary(self) -> ConfigFlowResult:
        assert self._requests is not None
        return self.async_show_menu(
            step_id="summary_high" if self._requests["high"] else "summary",
            menu_options=["save", "change"],
            description_placeholders=placeholders(self._requests),
        )

    async def async_step_summary(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self._summary()

    async def async_step_summary_high(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self._summary()

    async def async_step_save(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_create_entry(data=self._options)

    async def async_step_change(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self.async_step_init()
