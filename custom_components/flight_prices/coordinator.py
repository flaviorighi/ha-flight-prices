"""Coordinator for the Flight Prices integration."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta
from itertools import groupby
import logging
import random
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_GOOGLE_INTERVAL,
    CONF_RYANAIR_INTERVAL,
    DEFAULT_GOOGLE_HOURS,
    DEFAULT_RYANAIR_HOURS,
    DOMAIN,
    GOOGLE_DELAY,
    RYANAIR_DELAY,
    SOURCE_GOOGLE,
    SOURCE_RYANAIR,
    STORAGE_VERSION,
    TICK,
    TRIPS_PER_WEEK,
)
from .models import FlightData, SearchParams, SourceState, Trip, Week, WeekResult, cheapest_per_route
from .sources import SourceBlocked, SourceError
from .sources.google import GoogleSource, city_from_airport, plan as google_plan
from .sources.ryanair import RyanairSource, plan as ryanair_plan

_LOGGER = logging.getLogger(__name__)

type FlightPricesConfigEntry = ConfigEntry[FlightPricesCoordinator]

# A failed Ryanair search is tried again sooner than the next regular one.
RYANAIR_RETRY = timedelta(minutes=30)
# Google errors that are not a block, in a row, before the round stops.
GOOGLE_MAX_ERRORS = 5


class FlightPricesCoordinator(DataUpdateCoordinator[FlightData]):
    """Searches the sources when they are due and keeps what they found."""

    config_entry: FlightPricesConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: FlightPricesConfigEntry,
        ryanair: RyanairSource | None,
        google: GoogleSource | None,
    ) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=TICK)
        self.params = SearchParams.from_options(entry.options)
        self.ryanair = ryanair if SOURCE_RYANAIR in self.params.sources else None
        self.google = (
            google if SOURCE_GOOGLE in self.params.sources and self.params.destinations_for(SOURCE_GOOGLE) else None
        )
        self.intervals = {
            SOURCE_RYANAIR: timedelta(hours=entry.options.get(CONF_RYANAIR_INTERVAL, DEFAULT_RYANAIR_HOURS)),
            SOURCE_GOOGLE: timedelta(hours=entry.options.get(CONF_GOOGLE_INTERVAL, DEFAULT_GOOGLE_HOURS)),
        }
        self.states: dict[str, SourceState] = {}
        # City, country and country code of a destination, learned from Ryanair, for the trips found on Google.
        self.names: dict[str, list[str | None]] = {}
        self.google_running = False
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")

    @property
    def active_sources(self) -> list[str]:
        return [name for name, source in ((SOURCE_RYANAIR, self.ryanair), (SOURCE_GOOGLE, self.google)) if source]

    async def async_load(self) -> None:
        """What the sources found before a restart, unless the search has changed since."""
        stored = await self._store.async_load() or {}
        self.names = dict(stored.get("names", {}))
        for source in self.active_sources:
            fingerprint = self.params.fingerprint(source)
            saved = stored.get("sources", {}).get(source)
            state = SourceState.from_dict(saved) if saved else None
            self.states[source] = state if state and state.fingerprint == fingerprint else SourceState(fingerprint)

    async def _async_update_data(self) -> FlightData:
        now = dt_util.utcnow()
        weeks = self.params.upcoming_weeks(dt_util.now().date())
        if self.ryanair and self._due(SOURCE_RYANAIR, now):
            await self._async_search_ryanair(weeks, now)
        if self.google and not self.google_running and self._due(SOURCE_GOOGLE, now):
            self.google_running = True
            self.config_entry.async_create_background_task(
                self.hass, self._async_search_google(weeks), f"{DOMAIN}_google_{self.config_entry.entry_id}"
            )
        data = self._assemble(weeks)
        if not any(result.trips for result in data.weeks) and all(
            state.error and not state.last_success for state in self.states.values()
        ):
            # Nothing found ever and every source failed: let Home Assistant retry the setup.
            errors = "; ".join(f"{name}: {state.error}" for name, state in self.states.items())
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="update_failed", translation_placeholders={"error": errors}
            )
        return data

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

    async def _async_search_ryanair(self, weeks: list[Week], now: datetime) -> None:
        assert self.ryanair is not None
        state = self.states[SOURCE_RYANAIR]
        state.last_attempt = now
        state.weeks = len(weeks)
        found: list[Trip] = []
        searched: set[tuple[str, str]] = set()
        error: str | None = None
        try:
            for request in ryanair_plan(self.params, weeks):
                if searched or error:
                    await asyncio.sleep(RYANAIR_DELAY)
                try:
                    trips = await self.ryanair.search(
                        request.origin,
                        request.week.outbound,
                        request.week.inbound,
                        self.params.outbound_hours,
                        self.params.return_hours,
                        self.params.destinations,
                    )
                except SourceBlocked:
                    raise
                except SourceError as err:
                    error = str(err)
                    continue
                searched.add(request.key)
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
        await self._store.async_save(self._to_store())

    async def _async_search_google(self, weeks: list[Week]) -> None:
        assert self.google is not None
        google = self.google
        state = self.states[SOURCE_GOOGLE]
        state.last_attempt = dt_util.utcnow()
        state.weeks = len(weeks)
        params = self.params
        requests = errors = 0
        error: str | None = None

        async def search(*args: Any) -> list[Any]:
            nonlocal requests
            if requests:
                await asyncio.sleep(random.uniform(*GOOGLE_DELAY))
            requests += 1
            return await self.hass.async_add_executor_job(google.search, *args)

        try:
            for week, week_requests in groupby(google_plan(params, weeks), key=lambda request: request.week):
                for request in week_requests:
                    origin, destination = request.origin, request.destination
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
                        if (trip.outbound_date, trip.origin, trip.destination) != (week.outbound, origin, destination)
                    ]
                    if out and back:
                        state.trips.append(self._google_trip(destination, out[0], back[0], week))
                self._store.async_delay_save(self._to_store, 10)
                self.async_set_updated_data(self._assemble(params.upcoming_weeks(dt_util.now().date())))
        except SourceBlocked as err:
            error = str(err)
            _LOGGER.warning("Google Flights search stopped after %s requests: %s", requests, err)
        else:
            state.last_success = dt_util.utcnow()
            _LOGGER.debug("Google Flights search finished: %s requests", requests)
        finally:
            # Also when Home Assistant stops in the middle: what was found so far is saved.
            state.error = error
            self.google_running = False
            google.close()
            self._store.async_delay_save(self._to_store, 0)
        self.async_set_updated_data(self._assemble(params.upcoming_weeks(dt_util.now().date())))

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
            currency=self.hass.config.currency,
            outbound=out.leg,
            inbound=back.leg,
            link=link,
            country_code=(place and place.country_code) or code,
            return_link=return_link,
        )

    def _assemble(self, weeks: list[Week]) -> FlightData:
        # Countries are left out here, not in the searches: changing them needs no new search.
        excluded = {code.upper() for code in self.params.exclude_countries}
        results = []
        for week in weeks:
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

    def _named(self, trip: Trip) -> Trip:
        if (trip.city and trip.country_code) or trip.destination not in self.names:
            return trip
        city, country, code = [*self.names[trip.destination], None, None, None][:3]
        return replace(
            trip, city=trip.city or city, country=trip.country or country, country_code=trip.country_code or code
        )

    def _to_store(self) -> dict[str, Any]:
        today = dt_util.now().date()
        for state in self.states.values():
            state.trips = [trip for trip in state.trips if trip.outbound_date >= today]
        return {
            "sources": {name: state.as_dict() for name, state in self.states.items()},
            "names": self.names,
        }
