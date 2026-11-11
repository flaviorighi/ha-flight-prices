"""One search: its sources, when they are due, and what they found."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
import contextlib
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
import logging
import random
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiohttp

from . import const
from .const import (
    CONF_GOOGLE_INTERVAL,
    CONF_RYANAIR_INTERVAL,
    DEFAULT_GOOGLE_HOURS,
    DEFAULT_RYANAIR_HOURS,
    SOURCE_GOOGLE,
    SOURCE_RYANAIR,
    TRIPS_PER_WEEK,
)
from .models import FlightData, SearchParams, SourceState, Trip, Week, WeekResult, cheapest_per_route
from .sources import SourceBlocked, SourceError
from .sources.google import GoogleSource, city_from_airport
from .sources.ryanair import RyanairSource
from .store import Store

_LOGGER = logging.getLogger(__name__)

# A failed Ryanair search is tried again sooner than the next regular one.
RYANAIR_RETRY = timedelta(minutes=30)
# Google errors that are not a block, in a row, before the round stops.
GOOGLE_MAX_ERRORS = 5


def utcnow() -> datetime:
    return datetime.now(UTC)


class InvalidConfig(ValueError):
    """The search sent by a client cannot be searched."""


@dataclass(frozen=True)
class SearchConfig:
    """A search as a client sends it: its options, and the currency, language and time zone of the home."""

    options: Mapping[str, Any]
    currency: str
    language: str
    time_zone: str
    # The name of the search in the client, for the app's page: renaming it searches nothing again.
    title: str = field(default="", compare=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SearchConfig:
        try:
            config = cls(
                options=dict(data["options"]),
                currency=str(data["currency"]).upper(),
                language=str(data["language"]),
                time_zone=str(data["time_zone"]),
                title=str(data.get("title") or ""),
            )
            SearchParams.from_options(config.options)
            ZoneInfo(config.time_zone)
            for key, default in (
                (CONF_RYANAIR_INTERVAL, DEFAULT_RYANAIR_HOURS),
                (CONF_GOOGLE_INTERVAL, DEFAULT_GOOGLE_HOURS),
            ):
                if not 1 <= int(config.options.get(key, default)) <= 168:
                    raise ValueError(f"{key} out of range")
        except (KeyError, TypeError, ValueError, ZoneInfoNotFoundError) as err:
            raise InvalidConfig(f"invalid search: {err!r}") from err
        return config

    def as_dict(self) -> dict[str, Any]:
        return {
            "options": dict(self.options),
            "currency": self.currency,
            "language": self.language,
            "time_zone": self.time_zone,
            "title": self.title,
        }


class Search:
    """Searches the sources when they are due and keeps what they found."""

    def __init__(
        self,
        search_id: str,
        config: SearchConfig,
        store: Store,
        session: aiohttp.ClientSession,
        clock: Callable[[], datetime] = utcnow,
        on_google_request: Callable[[], None] | None = None,
    ) -> None:
        self.id = search_id
        # Every request to Google, of any search, counts towards what one connection can make in a day.
        self._on_google_request = on_google_request
        self.config = config
        self.params = SearchParams.from_options(config.options)
        self._store = store
        self._clock = clock
        self._tz = ZoneInfo(config.time_zone)
        self.ryanair = (
            RyanairSource(session, config.currency, config.language) if SOURCE_RYANAIR in self.params.sources else None
        )
        self.google = (
            GoogleSource(config.currency, config.language)
            if SOURCE_GOOGLE in self.params.sources and self.params.destinations_for(SOURCE_GOOGLE)
            else None
        )
        options = config.options
        self.intervals = {
            SOURCE_RYANAIR: timedelta(hours=int(options.get(CONF_RYANAIR_INTERVAL, DEFAULT_RYANAIR_HOURS))),
            SOURCE_GOOGLE: timedelta(hours=int(options.get(CONF_GOOGLE_INTERVAL, DEFAULT_GOOGLE_HOURS))),
        }
        self.states: dict[str, SourceState] = {}
        # City, country and country code of a destination, learned from Ryanair, for the trips found on Google.
        self.names: dict[str, list[str | None]] = {}
        self.google_running = False
        self._google_task: asyncio.Task[None] | None = None
        self._loop_task: asyncio.Task[None] | None = None
        # Changes whenever the results may have changed: clients can tell a new answer from the last one.
        self.updated = clock()

    @property
    def active_sources(self) -> list[str]:
        return [name for name, source in ((SOURCE_RYANAIR, self.ryanair), (SOURCE_GOOGLE, self.google)) if source]

    def _today(self) -> date:
        return self._clock().astimezone(self._tz).date()

    def _weeks(self) -> list[Week]:
        return self.params.upcoming_weeks(self._today())

    async def load(self, restore: Mapping[str, Any] | None = None) -> None:
        """What the sources found before a restart, unless the search has changed since.

        restore is what the integration had saved before the app existed, used when the app has nothing.
        """
        saved_here = await self._store.load_state(self.id)
        stored = saved_here or restore or {}
        try:
            names = dict(stored.get("names", {}))
            states = {
                source: SourceState.from_dict(saved)
                for source in self.active_sources
                if (saved := stored.get("sources", {}).get(source))
            }
        except (AttributeError, KeyError, TypeError, ValueError) as err:
            # Searching again is better than a search that never starts.
            _LOGGER.warning("Search %s: what was saved cannot be read (%r), starting empty", self.id, err)
            names, states = {}, {}
        self.names = names
        for source in self.active_sources:
            fingerprint = self.params.fingerprint(source)
            state = states.get(source)
            self.states[source] = state if state and state.fingerprint == fingerprint else SourceState(fingerprint)
        if not saved_here and restore:
            # Written at once: the client sends what it had only the first time, and a source may not be due
            # before the app restarts.
            await self._save()

    def start(self) -> None:
        """Search now and then whenever a source is due, until closed."""
        if self._loop_task is None:
            self._loop_task = asyncio.create_task(self._run(), name=f"search {self.id}")

    async def _run(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                _LOGGER.exception("Search %s failed", self.id)
            await asyncio.sleep(const.TICK.total_seconds())

    async def close(self) -> None:
        """Stop searching; a Google round in progress saves what it found so far."""
        for task in (self._loop_task, self._google_task):
            if task and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        self._loop_task = self._google_task = None

    async def tick(self) -> None:
        """Search the sources that are due; Google goes on in the background."""
        now = self._clock()
        weeks = self._weeks()
        if self.ryanair and self._due(SOURCE_RYANAIR, now):
            await self._search_ryanair(weeks, now)
        if self.google and not self.google_running and self._due(SOURCE_GOOGLE, now):
            self.google_running = True
            self.updated = self._clock()
            self._google_task = asyncio.create_task(self._search_google(weeks), name=f"search {self.id} google")

    async def wait_google(self) -> None:
        """For tests and shutdown: until the Google round in progress ends."""
        if self._google_task:
            await self._google_task

    def _due(self, source: str, now: datetime) -> bool:
        state = self.states[source]
        if state.last_attempt is None:
            return True
        # Weeks added in the options: searched now, not at the next interval.
        if state.weeks is not None and state.weeks < self.params.weeks:
            return True
        since = now - state.last_attempt
        if since >= self.intervals[source]:
            return True
        # A Google block waits for the next regular round; a Ryanair error is retried sooner.
        return source == SOURCE_RYANAIR and state.error is not None and since >= RYANAIR_RETRY

    async def _search_ryanair(self, weeks: list[Week], now: datetime) -> None:
        assert self.ryanair is not None
        state = self.states[SOURCE_RYANAIR]
        state.last_attempt = now
        state.weeks = len(weeks)
        found: list[Trip] = []
        searched: set[tuple[str, str]] = set()
        error: str | None = None
        try:
            for week in weeks:
                for origin in self.params.origins_for(SOURCE_RYANAIR):
                    if searched or error:
                        await asyncio.sleep(const.RYANAIR_DELAY)
                    try:
                        trips = await self.ryanair.search(
                            origin,
                            week.outbound,
                            week.inbound,
                            self.params.outbound_hours,
                            self.params.return_hours,
                            self.params.destinations,
                        )
                    except SourceBlocked:
                        raise
                    except SourceError as err:
                        error = str(err)
                        continue
                    searched.add((week.outbound.isoformat(), origin))
                    found.extend(trips)
        except SourceBlocked as err:
            error = str(err)
        if searched:
            # Searches that failed keep what the previous round found for them.
            kept = [trip for trip in state.trips if (trip.outbound_date.isoformat(), trip.origin) not in searched]
            state.trips = kept + found
            state.last_success = now
            for trip in found:
                self.names[trip.destination] = [trip.city, trip.country, trip.country_code]
        state.error = error
        if error:
            _LOGGER.warning("Ryanair search %s: %s", "incomplete" if searched else "failed", error)
        self.updated = self._clock()
        await self._save()

    async def _search_google(self, weeks: list[Week]) -> None:
        assert self.google is not None
        google = self.google
        state = self.states[SOURCE_GOOGLE]
        state.last_attempt = self._clock()
        state.weeks = len(weeks)
        params = self.params
        requests = errors = 0
        error: str | None = None

        async def search(*args: Any) -> list[Any]:
            nonlocal requests
            if requests:
                await asyncio.sleep(random.uniform(*const.GOOGLE_DELAY))
            requests += 1
            if self._on_google_request:
                self._on_google_request()
            return await asyncio.to_thread(google.search, *args)

        try:
            for week in weeks:
                for destination in params.destinations_for(SOURCE_GOOGLE):
                    for origin in params.origins_for(SOURCE_GOOGLE):
                        try:
                            out = await search(
                                week.outbound, origin, destination, params.outbound_hours, params.direct_only
                            )
                            back = (
                                await search(week.inbound, destination, origin, params.return_hours, params.direct_only)
                                if out
                                else []
                            )
                        except SourceBlocked:
                            raise
                        except SourceError as err:
                            errors += 1
                            error = str(err)
                            if errors >= GOOGLE_MAX_ERRORS:
                                raise SourceBlocked(f"{errors} errors in a row, the last: {err}") from err
                            continue
                        errors = 0
                        # This search replaces what the previous round found for it.
                        state.trips = [
                            trip
                            for trip in state.trips
                            if (trip.outbound_date, trip.origin, trip.destination)
                            != (week.outbound, origin, destination)
                        ]
                        if out and back:
                            state.trips.append(self._google_trip(destination, out[0], back[0], week))
                self.updated = self._clock()
                await self._save()
        except SourceBlocked as err:
            error = str(err)
            _LOGGER.warning("Google Flights search stopped after %s requests: %s", requests, err)
        else:
            state.last_success = self._clock()
            _LOGGER.info("Google Flights search finished: %s requests", requests)
        finally:
            # Also when the app stops in the middle: what was found so far is saved.
            state.error = error
            self.google_running = False
            self.updated = self._clock()
            google.close()
            await asyncio.shield(self._save())

    def _google_trip(self, destination: str, out: Any, back: Any, week: Week) -> Trip:
        assert self.google is not None
        place = out.place
        if place and place.country_code and destination not in self.names:
            # Also names the trips saved before Google described its places.
            self.names[destination] = [place.city, place.country, place.country_code]
        city, country, code = [*self.names.get(destination, []), None, None, None][:3]
        params = self.params
        origin = out.leg.origin
        there = (week.outbound, origin, destination, params.outbound_hours)
        back_home = (week.inbound, destination, origin, params.return_hours)
        if out.leg.airline == back.leg.airline:
            # One airline sells the return trip, often for less than two one-way tickets.
            link = self.google.link([there, back_home], params.direct_only)
            return_link = None
        else:
            # Two airlines are two tickets: a return search would not show this pair.
            link = self.google.link([there], params.direct_only)
            return_link = self.google.link([back_home], params.direct_only)
        return Trip(
            source=SOURCE_GOOGLE,
            destination=destination,
            # Google's own place, else Ryanair's names, else the city in Google's airport name.
            city=(place and place.city) or city or city_from_airport(out.destination_name),
            country=(place and place.country) or country,
            price=round(out.price + back.price, 2),
            currency=self.config.currency,
            outbound=out.leg,
            inbound=back.leg,
            link=link,
            country_code=(place and place.country_code) or code,
            return_link=return_link,
        )

    def data(self) -> FlightData:
        """The trips of each week, cheapest first."""
        # Countries are left out here, not in the searches: changing them needs no new search.
        excluded = {code.upper() for code in self.params.exclude_countries}
        results = []
        for week in self._weeks():
            trips = [
                named
                for state in self.states.values()
                for trip in state.trips
                if trip.outbound_date == week.outbound
                and trip.inbound.departure.date() == week.inbound
                and (named := self._named(trip)).country_code not in excluded
            ]
            best = cheapest_per_route(trips)
            found = len({trip.destination for trip in best})
            results.append(WeekResult(week, tuple(best[:TRIPS_PER_WEEK]), found))
        return FlightData(weeks=tuple(results), sources=dict(self.states))

    def result(self) -> dict[str, Any]:
        """What the API answers: the weeks with their trips, and the state of each source."""
        data = self.data()
        return {
            "id": self.id,
            "title": self.config.title,
            "updated": self.updated.isoformat(),
            "currency": self.config.currency,
            "weeks": [
                {
                    "number": result.week.number,
                    "outbound_date": result.week.outbound.isoformat(),
                    "return_date": result.week.inbound.isoformat(),
                    "destinations_found": result.found,
                    "trips": [trip.as_attributes() for trip in result.trips],
                }
                for result in data.weeks
            ],
            "sources": {
                name: {
                    "last_attempt": state.last_attempt.isoformat() if state.last_attempt else None,
                    "last_success": state.last_success.isoformat() if state.last_success else None,
                    "error": state.error,
                    "trips": len(state.trips),
                    "running": name == SOURCE_GOOGLE and self.google_running,
                }
                for name, state in data.sources.items()
            },
        }

    def _named(self, trip: Trip) -> Trip:
        if (trip.city and trip.country_code) or trip.destination not in self.names:
            return trip
        city, country, code = [*self.names[trip.destination], None, None, None][:3]
        return replace(
            trip, city=trip.city or city, country=trip.country or country, country_code=trip.country_code or code
        )

    async def _save(self) -> None:
        today = self._today()
        for state in self.states.values():
            state.trips = [trip for trip in state.trips if trip.outbound_date >= today]
        await self._store.save_state(
            self.id,
            {
                "sources": {name: state.as_dict() for name, state in self.states.items()},
                "names": self.names,
            },
        )
