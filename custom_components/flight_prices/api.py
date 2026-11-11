"""The Flight Prices app, where the searches run."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import API_VERSION, CONF_PASSWORD, CONF_URL

TIMEOUT = aiohttp.ClientTimeout(total=15)


class AppError(Exception):
    """The app refused what was asked; code says why, as in its answer."""

    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(message or code)
        self.code = code


class CannotConnect(AppError):
    """The app did not answer: not started, or at another address."""

    def __init__(self, message: str) -> None:
        super().__init__("cannot_connect", message)


class Incompatible(AppError):
    """The app speaks another version of the API: one of the two needs an update."""

    def __init__(self, version: str) -> None:
        super().__init__("incompatible", f"app version {version}")
        self.version = version


class FlightPricesApp:
    """Client of the app's HTTP API."""

    def __init__(self, session: aiohttp.ClientSession, url: str, password: str | None = None) -> None:
        self._session = session
        self.url = url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {password}"} if password else {}

    async def _request(self, method: str, path: str, json: Any = None) -> tuple[int, Any]:
        try:
            async with self._session.request(
                method, f"{self.url}{path}", json=json, headers=self._headers, timeout=TIMEOUT
            ) as response:
                data = await response.json(content_type=None) if response.status != 204 else None
                if response.status >= 400 and response.status != 404:
                    error = data if isinstance(data, dict) else {}
                    raise AppError(str(error.get("error", response.status)), error.get("message"))
                return response.status, data
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise CannotConnect(f"{type(err).__name__}: {err}") from err

    async def info(self) -> dict[str, Any]:
        """The version of the app; Incompatible when it speaks another API."""
        _status, data = await self._request("GET", "/api/info")
        if not isinstance(data, dict) or "version" not in data:
            raise CannotConnect("not a Flight Prices app")
        if data.get("api") != API_VERSION:
            raise Incompatible(str(data["version"]))
        return data

    async def count_requests(self, options: dict[str, Any], search_id: str | None = None) -> dict[str, Any]:
        """How many requests these options would make, alone and with the app's other searches.

        search_id is the search being changed: its own requests are not counted twice.
        """
        body: dict[str, Any] = {"options": options}
        if search_id:
            body["search_id"] = search_id
        _status, data = await self._request("POST", "/api/requests", body)
        return data

    async def get_search(self, search_id: str) -> dict[str, Any] | None:
        """What a search found; None when the app is not running it, for example after a restart."""
        status, data = await self._request("GET", f"/api/searches/{search_id}")
        return None if status == 404 else data

    async def put_search(self, search_id: str, search: dict[str, Any]) -> dict[str, Any]:
        """Run this search from now on; the same search sent again changes nothing."""
        _status, data = await self._request("PUT", f"/api/searches/{search_id}", search)
        return data

    async def delete_search(self, search_id: str) -> None:
        await self._request("DELETE", f"/api/searches/{search_id}")


def app_client(hass: HomeAssistant, data: Mapping[str, Any]) -> FlightPricesApp:
    """The app an entry, or a form, points to."""
    return FlightPricesApp(async_get_clientsession(hass), data[CONF_URL], data.get(CONF_PASSWORD))


def connection(data: Mapping[str, Any]) -> dict[str, Any]:
    """Where the app is and its password, as entries keep them: no empty password."""
    result: dict[str, Any] = {CONF_URL: str(data[CONF_URL]).strip().rstrip("/")}
    if password := data.get(CONF_PASSWORD):
        result[CONF_PASSWORD] = password
    return result
