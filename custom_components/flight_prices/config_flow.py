"""Config flow for the Flight Prices integration."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
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
)
from homeassistant.util import dt as dt_util

from .const import (
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
    CONF_RETURN_DAY,
    CONF_RETURN_FROM,
    CONF_RETURN_TO,
    CONF_RYANAIR_INTERVAL,
    CONF_SOURCES,
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
    DEFAULT_WEEKS,
    DOMAIN,
    GOOGLE_DELAY,
    GOOGLE_HIGH_REQUESTS_PER_DAY,
    GOOGLE_MAX_REQUESTS_PER_DAY,
    GOOGLE_MIN_HOURS,
    GUIDE_URL,
    MAX_WEEKS,
    SOURCE_GOOGLE,
    SOURCE_RYANAIR,
    SOURCES,
)
from .coordinator import FlightPricesConfigEntry
from .models import SearchParams
from .sources.google import plan as google_plan
from .sources.ryanair import plan as ryanair_plan

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


@dataclass(frozen=True)
class Requests:
    """The most requests a search makes: Google skips the return when the outbound found nothing."""

    google_round: int
    google_hours: int
    ryanair_round: int
    ryanair_hours: int

    @property
    def google_day(self) -> int:
        return -(-self.google_round * 24 // self.google_hours) if self.google_round else 0

    @property
    def google_minutes(self) -> int:
        """A round, at the average pause between two requests."""
        return round(self.google_round * sum(GOOGLE_DELAY) / 2 / 60)

    @property
    def high(self) -> bool:
        return self.google_day >= GOOGLE_HIGH_REQUESTS_PER_DAY


def count_requests(options: Mapping[str, Any]) -> Requests:
    """Per round: Google weeks x destinations x airports x 2 (out and back), Ryanair airports x weeks."""
    sources = options.get(CONF_SOURCES, ())
    params = SearchParams.from_options({CONF_ORIGINS: (), CONF_SOURCES: (), **options})
    weeks = params.upcoming_weeks(dt_util.now().date())
    google_requests = google_plan(params, weeks) if SOURCE_GOOGLE in sources else []
    return Requests(
        google_round=sum(request.max_requests for request in google_requests),
        google_hours=max(int(options.get(CONF_GOOGLE_INTERVAL, DEFAULT_GOOGLE_HOURS)), GOOGLE_MIN_HOURS),
        ryanair_round=len(ryanair_plan(params, weeks)) if SOURCE_RYANAIR in sources else 0,
        ryanair_hours=int(options.get(CONF_RYANAIR_INTERVAL, DEFAULT_RYANAIR_HOURS)),
    )


def placeholders(options: Mapping[str, Any]) -> dict[str, str]:
    """For the texts of the forms: the guide, the limit and what the search makes."""
    requests = count_requests(options)
    return {
        "guide_url": GUIDE_URL,
        "limit": str(GOOGLE_MAX_REQUESTS_PER_DAY),
        "count": str(requests.google_day),
        "google_round": str(requests.google_round),
        "google_day": str(requests.google_day),
        "google_minutes": str(requests.google_minutes),
        "google_hours": str(requests.google_hours),
        "ryanair_round": str(requests.ryanair_round),
        "ryanair_hours": str(requests.ryanair_hours),
    }


def validate(user_input: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """The options to store, and the errors to show."""
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
    for key in (CONF_RYANAIR_INTERVAL, CONF_GOOGLE_INTERVAL):
        if key in user_input:
            options[key] = int(user_input[key])
    # The interval cannot go under GOOGLE_MIN_HOURS: its field does not accept it.
    if count_requests(options).google_day > GOOGLE_MAX_REQUESTS_PER_DAY:
        # Many requests from one address get it a captcha from Google, for the whole home.
        errors.setdefault(CONF_GOOGLE_DESTINATIONS, "google_too_many")
    return options, errors


def _suggested(options: Mapping[str, Any]) -> dict[str, Any]:
    """Stored options as the form shows them: the days are strings in the selector."""
    values = dict(options)
    for key in (CONF_OUTBOUND_DAY, CONF_RETURN_DAY):
        if key in values:
            values[key] = str(values[key])
    return values


class FlightPricesConfigFlow(ConfigFlow, domain=DOMAIN):
    """One entry per search: from where, to where, on which days."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: FlightPricesConfigEntry) -> FlightPricesOptionsFlow:
        return FlightPricesOptionsFlow()

    def __init__(self) -> None:
        super().__init__()
        self._name = ""
        self._options: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        options: dict[str, Any] = {}
        if user_input is not None:
            options, errors = validate(user_input)
            if not errors:
                self._async_abort_entries_match(
                    {key: options[key] for key in (CONF_ORIGINS, CONF_DESTINATIONS, CONF_OUTBOUND_DAY, CONF_RETURN_DAY)}
                )
                self._name, self._options = user_input[CONF_NAME].strip(), options
                if count_requests(options).google_round:
                    return self._summary()
                return await self.async_step_save()
        suggested = user_input or ({CONF_NAME: self._name, **self._options} if self._options else {})
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, _suggested(suggested)),
            errors=errors,
            description_placeholders=placeholders(options),
        )

    def _summary(self) -> ConfigFlowResult:
        """What Google Flights will request, before saving: a form cannot count while it is filled in."""
        return self.async_show_menu(
            step_id="summary_high" if count_requests(self._options).high else "summary",
            menu_options=["save", "change"],
            description_placeholders=placeholders(self._options),
        )

    async def async_step_summary(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self._summary()

    async def async_step_summary_high(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self._summary()

    async def async_step_save(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_create_entry(title=self._name, data={}, options=self._options)

    async def async_step_change(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self.async_step_user()


class FlightPricesOptionsFlow(OptionsFlowWithReload):
    """Change the search; the entry reloads and searches again what changed."""

    def __init__(self) -> None:
        super().__init__()
        self._options: dict[str, Any] = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            options, errors = validate(user_input)
            if not errors:
                self._options = options
                if count_requests(options).google_round:
                    return self._summary()
                return await self.async_step_save()
        current = user_input or self._options or self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(OPTIONS_SCHEMA, _suggested(current)),
            errors=errors,
            # Opening Configure shows what the saved search makes; after an error, what was sent.
            description_placeholders=placeholders(validate(user_input)[0] if user_input else self.config_entry.options),
        )

    def _summary(self) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="summary_high" if count_requests(self._options).high else "summary",
            menu_options=["save", "change"],
            description_placeholders=placeholders(self._options),
        )

    async def async_step_summary(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self._summary()

    async def async_step_summary_high(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self._summary()

    async def async_step_save(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_create_entry(data=self._options)

    async def async_step_change(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self.async_step_init()
