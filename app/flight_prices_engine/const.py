"""Constants of the search engine."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

# The options of a search, as the integration sends them: the keys are part of the API.
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
# Google Flights has no published limit: too many automatic searches get the home's IP address a
# captcha. These limits are ours, kept well above what has run for weeks without a block (224
# requests a day, 20 to 30 seconds apart) and well below anything aggressive.
GOOGLE_MIN_HOURS: Final = 12
GOOGLE_MAX_REQUESTS_PER_DAY: Final = 300
# From here the summary before saving warns that the search is close to the limit.
GOOGLE_HIGH_REQUESTS_PER_DAY: Final = 200

# How often a search checks whether a source is due.
TICK: Final = timedelta(minutes=15)

# Ryanair answers in a fraction of a second; a short pause keeps the requests polite.
RYANAIR_DELAY: Final = 1.0
# Google Flights is read without an API: the requests are spread out, so a search of
# 160 pages takes about an hour, and a block stops it at once.
GOOGLE_DELAY: Final = (20.0, 30.0)

# Trips kept per week, at most one per destination and departure airport.
TRIPS_PER_WEEK: Final = 40

# The port of the API, inside the container.
DEFAULT_PORT: Final = 8765
