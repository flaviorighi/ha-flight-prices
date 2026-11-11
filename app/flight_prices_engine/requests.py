"""How many requests a search makes: shown before saving, and checked before searching."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .const import (
    CONF_DESTINATIONS,
    CONF_GOOGLE_DESTINATIONS,
    CONF_GOOGLE_INTERVAL,
    CONF_GOOGLE_ORIGINS,
    CONF_ORIGINS,
    CONF_RYANAIR_INTERVAL,
    CONF_SOURCES,
    CONF_WEEKS,
    DEFAULT_GOOGLE_HOURS,
    DEFAULT_RYANAIR_HOURS,
    DEFAULT_WEEKS,
    GOOGLE_DELAY,
    GOOGLE_HIGH_REQUESTS_PER_DAY,
    GOOGLE_MAX_REQUESTS_PER_DAY,
    GOOGLE_MIN_HOURS,
    SOURCE_GOOGLE,
    SOURCE_RYANAIR,
)


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

    @property
    def too_many(self) -> bool:
        # Many requests from one address get it a captcha from Google, for the whole home.
        return self.google_day > GOOGLE_MAX_REQUESTS_PER_DAY

    def as_dict(self) -> dict[str, Any]:
        return {
            "google_round": self.google_round,
            "google_hours": self.google_hours,
            "google_day": self.google_day,
            "google_minutes": self.google_minutes,
            "ryanair_round": self.ryanair_round,
            "ryanair_hours": self.ryanair_hours,
            "high": self.high,
            "too_many": self.too_many,
            "limit": GOOGLE_MAX_REQUESTS_PER_DAY,
        }


def count_requests(options: Mapping[str, Any]) -> Requests:
    """Per round: Google weeks x destinations x airports x 2 (out and back), Ryanair airports x weeks."""
    sources = options.get(CONF_SOURCES, ())
    weeks = int(options.get(CONF_WEEKS, DEFAULT_WEEKS))
    google_round = 0
    if SOURCE_GOOGLE in sources:
        destinations = options.get(CONF_GOOGLE_DESTINATIONS) or options.get(CONF_DESTINATIONS) or ()
        origins = options.get(CONF_GOOGLE_ORIGINS) or options.get(CONF_ORIGINS) or ()
        google_round = weeks * len(destinations) * len(origins) * 2
    return Requests(
        google_round=google_round,
        google_hours=max(int(options.get(CONF_GOOGLE_INTERVAL, DEFAULT_GOOGLE_HOURS)), GOOGLE_MIN_HOURS),
        ryanair_round=weeks * len(options.get(CONF_ORIGINS, ())) if SOURCE_RYANAIR in sources else 0,
        ryanair_hours=int(options.get(CONF_RYANAIR_INTERVAL, DEFAULT_RYANAIR_HOURS)),
    )
