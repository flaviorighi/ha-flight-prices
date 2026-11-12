"""Ryanair's fare finder, the API behind "cheapest fares" on ryanair.com.

One request per departure airport and week gives the cheapest return fare to every
destination, within the chosen departure hours. No key is needed. Fares are for one adult.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
import logging
from typing import Any
from urllib.parse import urlencode

import aiohttp

from ..const import SOURCE_RYANAIR
from ..models import Hours, Leg, SearchParams, Trip, Week
from . import SourceBlocked, SourceError, site_locale

_LOGGER = logging.getLogger(__name__)

URL = "https://services-api.ryanair.com/farfnd/v4/roundTripFares"
TIMEOUT = aiohttp.ClientTimeout(total=30)


@dataclass(frozen=True)
class RyanairRequest:
    """One request: the cheapest return fare to every destination, from one airport, for one week."""

    week: Week
    origin: str

    @property
    def key(self) -> tuple[str, str]:
        """What the request replaces among the trips of the previous round."""
        return (self.week.outbound.isoformat(), self.origin)


def plan(params: SearchParams, weeks: Iterable[Week]) -> list[RyanairRequest]:
    """The requests of a round, in the order they are made: the coordinator and the options count the same list."""
    return [RyanairRequest(week, origin) for week in weeks for origin in params.origins_for(SOURCE_RYANAIR)]


class RyanairSource:
    """Reads return fares from one airport."""

    def __init__(self, session: aiohttp.ClientSession, currency: str, language: str) -> None:
        self._session = session
        self._currency = currency
        self._country, self._language = site_locale(language)

    async def search(
        self,
        origin: str,
        outbound: date,
        inbound: date,
        outbound_hours: Hours,
        return_hours: Hours,
        destinations: Collection[str] = (),
    ) -> list[Trip]:
        """Cheapest trip to each destination; all of them when destinations is empty."""
        params = {
            "departureAirportIataCode": origin,
            "outboundDepartureDateFrom": outbound.isoformat(),
            "outboundDepartureDateTo": outbound.isoformat(),
            "inboundDepartureDateFrom": inbound.isoformat(),
            "inboundDepartureDateTo": inbound.isoformat(),
            "outboundDepartureTimeFrom": outbound_hours.start_text,
            "outboundDepartureTimeTo": outbound_hours.end_text,
            "inboundDepartureTimeFrom": return_hours.start_text,
            "inboundDepartureTimeTo": return_hours.end_text,
            "currency": self._currency,
            "market": f"{self._language}-{self._country}",
        }
        try:
            async with self._session.get(URL, params=params, timeout=TIMEOUT) as response:
                if response.status in (403, 429):
                    raise SourceBlocked(f"Ryanair answered HTTP {response.status}")
                if response.status != 200:
                    raise SourceError(f"Ryanair answered HTTP {response.status}")
                payload = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise SourceError(f"Ryanair did not answer: {err}") from err
        wanted = {code.upper() for code in destinations}
        trips = []
        for fare in payload.get("fares") or ():
            try:
                trip = self._trip(fare, wanted)
            except (KeyError, TypeError, ValueError) as err:
                _LOGGER.debug("Skipping a Ryanair fare that could not be read: %s", err)
                continue
            if trip is not None:
                trips.append(trip)
        return trips

    def _trip(self, fare: Mapping[str, Any], wanted: set[str]) -> Trip | None:
        out, back = fare["outbound"], fare["inbound"]
        arrival = out["arrivalAirport"]
        city = arrival.get("city") or {}
        # A destination in the list can be the airport (STN) or its city (LON).
        codes = [arrival["iataCode"], city.get("macCode")]
        if wanted:
            destination = next((code for code in codes if code in wanted), None)
            if destination is None:
                return None
        else:
            destination = city.get("macCode") or arrival["iataCode"]
        price = fare["summary"]["price"]
        outbound, inbound = _leg(out), _leg(back)
        return Trip(
            source=SOURCE_RYANAIR,
            destination=destination,
            city=city.get("name") or arrival.get("name"),
            country=arrival.get("countryName"),
            price=round(float(price["value"]), 2),
            currency=price.get("currencyCode") or self._currency,
            outbound=outbound,
            inbound=inbound,
            link=self.link(outbound, inbound),
            country_code=(city.get("countryCode") or "").upper() or None,
        )

    def link(self, outbound: Leg, inbound: Leg) -> str:
        query = urlencode(
            {
                "adults": 1,
                "teens": 0,
                "children": 0,
                "infants": 0,
                "dateOut": outbound.departure.date().isoformat(),
                "dateIn": inbound.departure.date().isoformat(),
                "isConnectedFlight": "false",
                "isReturn": "true",
                "discount": 0,
                "originIata": outbound.origin,
                "destinationIata": outbound.destination,
            }
        )
        return f"https://www.ryanair.com/{self._country}/{self._language}/trip/flights/select?{query}"


def _leg(flight: Mapping[str, Any]) -> Leg:
    return Leg(
        origin=flight["departureAirport"]["iataCode"],
        destination=flight["arrivalAirport"]["iataCode"],
        departure=datetime.fromisoformat(flight["departureDate"]),
        arrival=datetime.fromisoformat(flight["arrivalDate"]),
        flight_numbers=(flight["flightNumber"],),
        airline="Ryanair",
    )
