"""Constants for the Flight Prices integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "flight_prices"
# Linked from the setup and options forms.
GUIDE_URL: Final = "https://github.com/flaviorighi/ha-flight-prices/blob/main/docs/configuration.md"

CONF_ORIGINS: Final = "origins"
# Empty means anywhere: every destination the sources fly to.
CONF_DESTINATIONS: Final = "destinations"
CONF_SOURCES: Final = "sources"
# Departure airports searched on Google Flights; empty means all of them.
CONF_GOOGLE_ORIGINS: Final = "google_origins"
# Destinations searched on Google Flights; empty means the destinations above.
CONF_GOOGLE_DESTINATIONS: Final = "google_destinations"
CONF_WEEKS: Final = "weeks"
CONF_OUTBOUND_DAY: Final = "outbound_day"
CONF_OUTBOUND_FROM: Final = "outbound_from"
CONF_OUTBOUND_TO: Final = "outbound_to"
CONF_RETURN_DAY: Final = "return_day"
CONF_RETURN_FROM: Final = "return_from"
CONF_RETURN_TO: Final = "return_to"
CONF_DIRECT_ONLY: Final = "direct_only"
# ISO codes of countries left out, such as IT for flights within Italy.
CONF_EXCLUDE_COUNTRIES: Final = "exclude_countries"
CONF_RYANAIR_INTERVAL: Final = "ryanair_interval"
CONF_GOOGLE_INTERVAL: Final = "google_interval"

SOURCE_RYANAIR: Final = "ryanair"
SOURCE_GOOGLE: Final = "google"
SOURCES: Final = (SOURCE_RYANAIR, SOURCE_GOOGLE)

DEFAULT_WEEKS: Final = 8
MAX_WEEKS: Final = 12
# Friday evening out, Sunday afternoon or evening back. Days follow date.weekday().
DEFAULT_OUTBOUND_DAY: Final = 4
DEFAULT_OUTBOUND_FROM: Final = 19
DEFAULT_OUTBOUND_TO: Final = 24
DEFAULT_RETURN_DAY: Final = 6
DEFAULT_RETURN_FROM: Final = 14
DEFAULT_RETURN_TO: Final = 24
DEFAULT_DIRECT_ONLY: Final = True
DEFAULT_RYANAIR_HOURS: Final = 3
DEFAULT_GOOGLE_HOURS: Final = 24
# Google Flights has no published limit: the app refuses more than its limit a day, and an
# interval under this one. The field of the interval does not go lower.
GOOGLE_MIN_HOURS: Final = 12

# The searches run in the app: the integration asks it for what they found this often.
UPDATE_INTERVAL: Final = timedelta(minutes=1)
# Where the app is: http://<host>:<port>, from the Supervisor's discovery or typed in.
CONF_URL: Final = "url"
# Only when the app has one: the Supervisor's discovery passes it, or it is typed in.
CONF_PASSWORD: Final = "password"
DEFAULT_URL: Final = "http://localhost:8765"
# The version of the app's API this integration speaks.
API_VERSION: Final = 1
# Installing the app, linked from the forms and the repair.
APP_URL: Final = "https://github.com/flaviorighi/ha-flight-prices#installation"

# Trips in the attributes of a week sensor, cheapest first.
TRIPS_IN_ATTRIBUTES: Final = 30

# What the integration saved before the app existed, sent to the app once.
LEGACY_STORAGE_VERSION: Final = 1
