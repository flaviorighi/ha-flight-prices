"""Data shared by the sources and the searches."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import hashlib
import json
from typing import Any

from .const import (
    CONF_DESTINATIONS,
    CONF_DIRECT_ONLY,
    CONF_EXCLUDE_COUNTRIES,
    CONF_GOOGLE_DESTINATIONS,
    CONF_GOOGLE_ORIGINS,
    CONF_ORIGINS,
    CONF_OUTBOUND_DAY,
    CONF_OUTBOUND_FROM,
    CONF_OUTBOUND_TO,
    CONF_RETURN_DAY,
    CONF_RETURN_FROM,
    CONF_RETURN_TO,
    CONF_SOURCES,
    CONF_WEEKS,
    DEFAULT_DIRECT_ONLY,
    DEFAULT_OUTBOUND_DAY,
    DEFAULT_OUTBOUND_FROM,
    DEFAULT_OUTBOUND_TO,
    DEFAULT_RETURN_DAY,
    DEFAULT_RETURN_FROM,
    DEFAULT_RETURN_TO,
    DEFAULT_WEEKS,
    SOURCE_RYANAIR,
)


@dataclass(frozen=True, kw_only=True)
class Leg:
    """One way of a trip: one flight, or several with stops."""

    origin: str
    destination: str
    # Local times of the airports, as the airlines publish them.
    departure: datetime
    arrival: datetime
    flight_numbers: tuple[str, ...]
    airline: str
    stops: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "from": self.origin,
            "to": self.destination,
            "departure": self.departure.isoformat(timespec="minutes"),
            "arrival": self.arrival.isoformat(timespec="minutes"),
            "flights": " ".join(self.flight_numbers),
            "airline": self.airline,
            "stops": self.stops,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Leg:
        return cls(
            origin=data["from"],
            destination=data["to"],
            departure=datetime.fromisoformat(data["departure"]),
            arrival=datetime.fromisoformat(data["arrival"]),
            flight_numbers=tuple(data["flights"].split()),
            airline=data["airline"],
            stops=data["stops"],
        )


@dataclass(frozen=True, kw_only=True)
class Trip:
    """A return trip for one week, with its total price for one adult."""

    source: str
    # The code the trip is grouped by: the one in the list of destinations, or the city.
    destination: str
    city: str | None
    country: str | None
    price: float
    currency: str
    outbound: Leg
    inbound: Leg
    link: str
    # ISO code of the destination's country, upper case.
    country_code: str | None = None
    # Two tickets, as with two airlines on Google: link is the outbound, this the return.
    return_link: str | None = None

    @property
    def origin(self) -> str:
        return self.outbound.origin

    @property
    def outbound_date(self) -> date:
        return self.outbound.departure.date()

    @property
    def flights_key(self) -> tuple[tuple[str, ...], date, tuple[str, ...], date]:
        """The same flights found by two sources."""
        return (
            self.outbound.flight_numbers,
            self.outbound_date,
            self.inbound.flight_numbers,
            self.inbound.departure.date(),
        )

    @property
    def airline(self) -> str:
        if self.outbound.airline == self.inbound.airline:
            return self.outbound.airline
        return f"{self.outbound.airline} / {self.inbound.airline}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "destination": self.destination,
            "city": self.city,
            "country": self.country,
            "country_code": self.country_code,
            "price": self.price,
            "currency": self.currency,
            "outbound": self.outbound.as_dict(),
            "return": self.inbound.as_dict(),
            "link": self.link,
            "return_link": self.return_link,
        }

    def as_attributes(self) -> dict[str, Any]:
        """The trip as the dashboard reads it."""
        return {
            "destination": self.destination,
            "city": self.city or self.inbound.origin,
            "country": self.country,
            "country_code": self.country_code,
            "origin": self.origin,
            "price": self.price,
            "airline": self.airline,
            "source": self.source,
            "outbound": self.outbound.as_dict(),
            "return": self.inbound.as_dict(),
            "link": self.link,
            "return_link": self.return_link,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Trip:
        return cls(
            source=data["source"],
            destination=data["destination"],
            city=data["city"],
            country=data["country"],
            price=data["price"],
            currency=data["currency"],
            outbound=Leg.from_dict(data["outbound"]),
            inbound=Leg.from_dict(data["return"]),
            link=data["link"],
            country_code=data.get("country_code"),
            return_link=data.get("return_link"),
        )


@dataclass(frozen=True)
class Hours:
    """Departures from this hour to that one; 24 is midnight at the end of the day."""

    start: int
    end: int

    def contains(self, moment: datetime) -> bool:
        minutes = moment.hour * 60 + moment.minute
        return self.start * 60 <= minutes < self.end * 60

    @property
    def start_text(self) -> str:
        return f"{self.start:02d}:00"

    @property
    def end_text(self) -> str:
        return "23:59" if self.end >= 24 else f"{self.end:02d}:00"


@dataclass(frozen=True)
class Week:
    """The dates of one trip: out on the outbound day, back on the return day."""

    number: int
    outbound: date
    inbound: date


@dataclass(frozen=True, kw_only=True)
class SearchParams:
    """What a config entry searches for."""

    origins: tuple[str, ...]
    destinations: tuple[str, ...]
    sources: tuple[str, ...]
    weeks: int
    outbound_day: int
    outbound_hours: Hours
    return_day: int
    return_hours: Hours
    direct_only: bool
    exclude_countries: tuple[str, ...] = ()
    google_origins: tuple[str, ...] = ()
    google_destinations: tuple[str, ...] = ()

    @classmethod
    def from_options(cls, options: Mapping[str, Any]) -> SearchParams:
        return cls(
            origins=tuple(options[CONF_ORIGINS]),
            destinations=tuple(options.get(CONF_DESTINATIONS, ())),
            sources=tuple(options[CONF_SOURCES]),
            weeks=int(options.get(CONF_WEEKS, DEFAULT_WEEKS)),
            outbound_day=int(options.get(CONF_OUTBOUND_DAY, DEFAULT_OUTBOUND_DAY)),
            outbound_hours=Hours(
                int(options.get(CONF_OUTBOUND_FROM, DEFAULT_OUTBOUND_FROM)),
                int(options.get(CONF_OUTBOUND_TO, DEFAULT_OUTBOUND_TO)),
            ),
            return_day=int(options.get(CONF_RETURN_DAY, DEFAULT_RETURN_DAY)),
            return_hours=Hours(
                int(options.get(CONF_RETURN_FROM, DEFAULT_RETURN_FROM)),
                int(options.get(CONF_RETURN_TO, DEFAULT_RETURN_TO)),
            ),
            direct_only=bool(options.get(CONF_DIRECT_ONLY, DEFAULT_DIRECT_ONLY)),
            exclude_countries=tuple(options.get(CONF_EXCLUDE_COUNTRIES, ())),
            google_origins=tuple(options.get(CONF_GOOGLE_ORIGINS, ())),
            google_destinations=tuple(options.get(CONF_GOOGLE_DESTINATIONS, ())),
        )

    @property
    def anywhere(self) -> bool:
        return not self.destinations

    def origins_for(self, source: str) -> tuple[str, ...]:
        """The departure airports a source searches from."""
        if source != SOURCE_RYANAIR and self.google_origins:
            return self.google_origins
        return self.origins

    def destinations_for(self, source: str) -> tuple[str, ...]:
        """The destinations a source searches; empty means anywhere (Ryanair only)."""
        if source != SOURCE_RYANAIR and self.google_destinations:
            return self.google_destinations
        return self.destinations

    @property
    def all_destinations(self) -> tuple[str, ...]:
        """Every destination of a list, of any source."""
        return tuple(dict.fromkeys((*self.destinations, *self.google_destinations)))

    def fingerprint(self, source: str) -> str:
        """Changes when a source would search for something else."""
        what: dict[str, Any] = {
            # Raised when saved trips lack something new: 2 added the country code.
            "version": 2,
            "origins": sorted(self.origins_for(source)),
            "destinations": sorted(self.destinations_for(source)),
            "days": [self.outbound_day, self.return_day],
            "hours": [
                self.outbound_hours.start,
                self.outbound_hours.end,
                self.return_hours.start,
                self.return_hours.end,
            ],
        }
        # Ryanair only flies direct.
        if source != SOURCE_RYANAIR:
            what["direct_only"] = self.direct_only
        return hashlib.sha256(json.dumps(what, sort_keys=True).encode()).hexdigest()[:16]

    def upcoming_weeks(self, today: date) -> list[Week]:
        """The next weeks, starting with the one whose outbound day is today or after."""
        first = today + timedelta(days=(self.outbound_day - today.weekday()) % 7)
        stay = (self.return_day - self.outbound_day) % 7 or 7
        return [
            Week(number, first + timedelta(weeks=number - 1), first + timedelta(weeks=number - 1, days=stay))
            for number in range(1, self.weeks + 1)
        ]


@dataclass
class SourceState:
    """What one source found, and when it last searched."""

    fingerprint: str | None = None
    last_attempt: datetime | None = None
    last_success: datetime | None = None
    error: str | None = None
    trips: list[Trip] = field(default_factory=list)
    # How many weeks the last search covered: with more weeks in the options it searches again.
    weeks: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "fingerprint": self.fingerprint,
            "weeks": self.weeks,
            "last_attempt": self.last_attempt.isoformat() if self.last_attempt else None,
            "last_success": self.last_success.isoformat() if self.last_success else None,
            "error": self.error,
            "trips": [trip.as_dict() for trip in self.trips],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SourceState:
        return cls(
            fingerprint=data.get("fingerprint"),
            last_attempt=datetime.fromisoformat(data["last_attempt"]) if data.get("last_attempt") else None,
            last_success=datetime.fromisoformat(data["last_success"]) if data.get("last_success") else None,
            error=data.get("error"),
            trips=[Trip.from_dict(trip) for trip in data.get("trips", ())],
            weeks=data.get("weeks"),
        )


@dataclass(frozen=True)
class WeekResult:
    """The cheapest trips of one week, at most one per destination, cheapest first."""

    week: Week
    trips: tuple[Trip, ...]
    # Destinations found in all, also beyond the trips kept.
    found: int = 0


@dataclass(frozen=True)
class FlightData:
    """What the coordinator hands to the sensors."""

    weeks: tuple[WeekResult, ...]
    sources: Mapping[str, SourceState]


def cheapest_per_route(trips: Iterable[Trip]) -> list[Trip]:
    """One trip per destination and departure airport, the cheapest, then sorted by price."""
    best: dict[tuple[str, str], Trip] = {}
    for trip in trips:
        key = (trip.destination, trip.origin)
        if (current := best.get(key)) is None or trip.price < current.price:
            best[key] = trip
    return sorted(best.values(), key=lambda trip: (trip.price, trip.destination, trip.origin))
