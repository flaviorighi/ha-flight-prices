"""The HTTP API the integration talks to, and the app's page."""

from __future__ import annotations

import asyncio
import base64
import binascii
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
import hmac
from importlib import resources
import logging
from typing import Any

import aiohttp
from aiohttp import web

from . import __version__
from .const import (
    CONF_GOOGLE_INTERVAL,
    GOOGLE_HIGH_REQUESTS_PER_DAY,
    GOOGLE_MAX_REQUESTS_PER_DAY,
    GOOGLE_MIN_HOURS,
)
from .requests import count_requests
from .search import InvalidConfig, Search, SearchConfig, utcnow
from .store import Store, valid_id

_LOGGER = logging.getLogger(__name__)

ENGINE: web.AppKey[Engine] = web.AppKey("engine")
# Raised when the API changes in a way an older integration cannot follow.
API_VERSION = 1
# Where the Supervisor's ingress proxy comes from: Home Assistant has already checked who is asking.
INGRESS_IP = "172.30.32.2"
PAGE = "index.html"


class Engine:
    """The searches the clients asked for: each one searches on its own until it is changed or deleted."""

    def __init__(self, store: Store, session: aiohttp.ClientSession, clock: Callable[[], datetime] = utcnow) -> None:
        self.store = store
        self.session = session
        self.clock = clock
        # Running: sent by a client since the app started.
        self.searches: dict[str, Search] = {}
        # Every search saved, running or waiting for its client after a restart: all of them count for Google.
        self.configs: dict[str, SearchConfig] = {}
        self._google_requests: deque[datetime] = deque()
        self._lock = asyncio.Lock()

    async def load(self) -> None:
        """The searches saved before a restart, for the totals; they run when their client sends them again."""
        for search_id in await self.store.ids():
            saved = await self.store.load_config(search_id)
            try:
                self.configs[search_id] = SearchConfig.from_dict(saved or {})
            except InvalidConfig as err:
                _LOGGER.warning("Search %s: saved search cannot be read (%s)", search_id, err)

    def google_day(self, exclude: str | None = None) -> int:
        """The most Google requests a day of the saved searches, all from the same connection."""
        return sum(
            count_requests(config.options).google_day
            for search_id, config in self.configs.items()
            if search_id != exclude
        )

    def google_requests_24h(self) -> int:
        """Requests made to Google in the last 24 hours, since the app started."""
        since = self.clock() - timedelta(hours=24)
        while self._google_requests and self._google_requests[0] < since:
            self._google_requests.popleft()
        return len(self._google_requests)

    def _google_request(self) -> None:
        self._google_requests.append(self.clock())

    def check(self, search_id: str | None, options: dict[str, Any]) -> dict[str, Any]:
        """What these options would request, alone and with the other searches."""
        requests = count_requests(options)
        others = self.google_day(exclude=search_id)
        total = others + requests.google_day
        previous = self.configs.get(search_id) if search_id else None
        # A search sent again as it was never fails because of the others: only more requests do.
        grows = previous is None or requests.google_day > count_requests(previous.options).google_day
        return {
            **requests.as_dict(),
            "other_day": others,
            "total_day": total,
            # The warning before saving is about the connection: it looks at the total.
            "high": total >= GOOGLE_HIGH_REQUESTS_PER_DAY,
            "too_many_total": grows and requests.google_day > 0 and total > GOOGLE_MAX_REQUESTS_PER_DAY,
        }

    async def put(self, search_id: str, body: dict[str, Any]) -> Search:
        """Search for this from now on; the same search sent again changes nothing."""
        config = SearchConfig.from_dict(body)
        if int(config.options.get(CONF_GOOGLE_INTERVAL, GOOGLE_MIN_HOURS)) < GOOGLE_MIN_HOURS:
            raise InvalidConfig("google_interval_too_short")
        async with self._lock:
            requests = self.check(search_id, dict(config.options))
            if requests["too_many"]:
                raise InvalidConfig("google_too_many")
            if requests["too_many_total"]:
                raise InvalidConfig("google_too_many_total")
            current = self.searches.get(search_id)
            if current and current.config == config:
                if current.config.title != config.title:
                    current.config = self.configs[search_id] = config
                    await self.store.save_config(search_id, config.as_dict())
                return current
            if current:
                await current.close()
            await self.store.save_config(search_id, config.as_dict())
            self.configs[search_id] = config
            search = Search(search_id, config, self.store, self.session, self.clock, self._google_request)
            await search.load(body.get("restore"))
            search.start()
            self.searches[search_id] = search
            _LOGGER.info("Search %s (%s): %s", search_id, config.title, "changed" if current else "started")
            return search

    async def delete(self, search_id: str) -> None:
        """Stop the search and forget what it found."""
        async with self._lock:
            if search := self.searches.pop(search_id, None):
                await search.close()
            self.configs.pop(search_id, None)
            await self.store.delete(search_id)
        _LOGGER.info("Search %s: deleted", search_id)

    def summary(self) -> list[dict[str, Any]]:
        """Every saved search, for the page: running or waiting for its client."""
        return [
            {
                "id": search_id,
                "title": config.title,
                "running": search_id in self.searches,
                "google_day": count_requests(config.options).google_day,
            }
            for search_id, config in sorted(self.configs.items(), key=lambda item: item[1].title.casefold())
        ]

    async def close(self) -> None:
        async with self._lock:
            await asyncio.gather(*(search.close() for search in self.searches.values()))
            self.searches.clear()


def _error(status: int, code: str, message: str | None = None) -> web.Response:
    return web.json_response({"error": code, "message": message or code}, status=status)


def _search_id(request: web.Request) -> str:
    search_id = request.match_info["search_id"]
    if not valid_id(search_id):
        raise web.HTTPBadRequest(text='{"error": "invalid_id"}', content_type="application/json")
    return search_id


async def _json(request: web.Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except ValueError as err:
        raise web.HTTPBadRequest(text='{"error": "invalid_json"}', content_type="application/json") from err
    if not isinstance(body, dict):
        raise web.HTTPBadRequest(text='{"error": "invalid_json"}', content_type="application/json")
    return body


async def info(request: web.Request) -> web.Response:
    engine = request.app[ENGINE]
    return web.json_response(
        {
            "version": __version__,
            "api": API_VERSION,
            "searches": sorted(engine.searches),
            "google": {
                "limit": GOOGLE_MAX_REQUESTS_PER_DAY,
                "day": engine.google_day(),
                "last_24h": engine.google_requests_24h(),
            },
        }
    )


async def list_searches(request: web.Request) -> web.Response:
    return web.json_response(request.app[ENGINE].summary())


async def get_search(request: web.Request) -> web.Response:
    search_id = _search_id(request)
    # Not running here, for example after a restart of the app: the client sends it again.
    if (search := request.app[ENGINE].searches.get(search_id)) is None:
        return _error(404, "not_found")
    return web.json_response(search.result())


async def put_search(request: web.Request) -> web.Response:
    search_id = _search_id(request)
    body = await _json(request)
    try:
        search = await request.app[ENGINE].put(search_id, body)
    except InvalidConfig as err:
        known = ("google_too_many", "google_too_many_total", "google_interval_too_short")
        code = str(err) if str(err) in known else "invalid_search"
        return _error(400, code, str(err))
    return web.json_response(search.result())


async def delete_search(request: web.Request) -> web.Response:
    await request.app[ENGINE].delete(_search_id(request))
    return web.Response(status=204)


async def request_count(request: web.Request) -> web.Response:
    """How many requests these options would make, alone and with the other searches, for the summary."""
    body = await _json(request)
    search_id = body.get("search_id")
    if search_id is not None and not (isinstance(search_id, str) and valid_id(search_id)):
        return _error(400, "invalid_id")
    return web.json_response(request.app[ENGINE].check(search_id, body.get("options") or {}))


async def page(request: web.Request) -> web.Response:
    html = resources.files(__package__).joinpath("web", PAGE).read_text(encoding="utf-8")
    return web.Response(text=html, content_type="text/html", headers={"Cache-Control": "no-cache"})


def _authorized(request: web.Request, password: str) -> bool:
    """A Bearer token, as the integration sends it, or the browser's Basic login with any user name."""
    header = request.headers.get("Authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() == "bearer":
        given = value
    elif scheme.lower() == "basic":
        try:
            given = base64.b64decode(value, validate=True).decode().partition(":")[2]
        except (binascii.Error, UnicodeDecodeError):
            return False
    else:
        return False
    return hmac.compare_digest(given.encode(), password.encode())


def _auth(password: str | None, trusted: str | None) -> Callable[..., Awaitable[web.StreamResponse]]:
    @web.middleware
    async def middleware(
        request: web.Request, handler: Callable[[web.Request], Awaitable[web.StreamResponse]]
    ) -> web.StreamResponse:
        if not password or (trusted and request.remote == trusted) or _authorized(request, password):
            return await handler(request)
        # The browser asks for the password; the integration gets a code it can show.
        return web.json_response(
            {"error": "invalid_auth", "message": "invalid_auth"},
            status=401,
            headers={"WWW-Authenticate": 'Basic realm="Flight Prices", charset="UTF-8"'},
        )

    return middleware


def create_app(engine: Engine, password: str | None = None, trusted: str | None = None) -> web.Application:
    """The API and the page; with a password, both need it, except from trusted (the ingress proxy)."""
    app = web.Application(middlewares=[_auth(password, trusted)])
    app[ENGINE] = engine
    app.add_routes(
        [
            web.get("/", page),
            web.get("/api/info", info),
            web.post("/api/requests", request_count),
            web.get("/api/searches", list_searches),
            web.get("/api/searches/{search_id}", get_search),
            web.put("/api/searches/{search_id}", put_search),
            web.delete("/api/searches/{search_id}", delete_search),
        ]
    )

    async def close(app: web.Application) -> None:
        await app[ENGINE].close()

    app.on_shutdown.append(close)
    return app
