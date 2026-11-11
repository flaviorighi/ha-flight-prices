"""The Flight Prices app, where the searches run."""

from __future__ import annotations

from typing import Any

import aiohttp

from .const import API_VERSION

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

    def __init__(self, session: aiohttp.ClientSession, url: str) -> None:
        self._session = session
        self.url = url.rstrip("/")

    async def _request(self, method: str, path: str, json: Any = None) -> tuple[int, Any]:
        try:
            async with self._session.request(method, f"{self.url}{path}", json=json, timeout=TIMEOUT) as response:
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

    async def count_requests(self, options: dict[str, Any]) -> dict[str, Any]:
        """How many requests these options would make, as the app counts them."""
        _status, data = await self._request("POST", "/api/requests", {"options": options})
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
