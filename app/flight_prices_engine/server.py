"""The HTTP API the integration talks to."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
import logging
from typing import Any

import aiohttp
from aiohttp import web

from . import __version__
from .const import CONF_GOOGLE_INTERVAL, GOOGLE_MIN_HOURS
from .requests import count_requests
from .search import InvalidConfig, Search, SearchConfig, utcnow
from .store import Store, valid_id

_LOGGER = logging.getLogger(__name__)

ENGINE: web.AppKey[Engine] = web.AppKey("engine")
# Raised when the API changes in a way an older integration cannot follow.
API_VERSION = 1


class Engine:
    """The searches the clients asked for: each one searches on its own until it is changed or deleted."""

    def __init__(self, store: Store, session: aiohttp.ClientSession, clock: Callable[[], datetime] = utcnow) -> None:
        self.store = store
        self.session = session
        self.clock = clock
        self.searches: dict[str, Search] = {}
        self._lock = asyncio.Lock()

    async def put(self, search_id: str, body: dict[str, Any]) -> Search:
        """Search for this from now on; the same search sent again changes nothing."""
        config = SearchConfig.from_dict(body)
        requests = count_requests(config.options)
        if requests.too_many:
            raise InvalidConfig("google_too_many")
        if int(config.options.get(CONF_GOOGLE_INTERVAL, GOOGLE_MIN_HOURS)) < GOOGLE_MIN_HOURS:
            raise InvalidConfig("google_interval_too_short")
        async with self._lock:
            current = self.searches.get(search_id)
            if current and current.config == config:
                return current
            if current:
                await current.close()
            await self.store.save_config(search_id, config.as_dict())
            search = Search(search_id, config, self.store, self.session, self.clock)
            await search.load(body.get("restore"))
            search.start()
            self.searches[search_id] = search
            _LOGGER.info("Search %s: %s", search_id, "changed" if current else "started")
            return search

    async def delete(self, search_id: str) -> None:
        """Stop the search and forget what it found."""
        async with self._lock:
            if search := self.searches.pop(search_id, None):
                await search.close()
            await self.store.delete(search_id)
        _LOGGER.info("Search %s: deleted", search_id)

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
    return web.json_response({"version": __version__, "api": API_VERSION, "searches": sorted(engine.searches)})


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
        code = str(err) if str(err) in ("google_too_many", "google_interval_too_short") else "invalid_search"
        return _error(400, code, str(err))
    return web.json_response(search.result())


async def delete_search(request: web.Request) -> web.Response:
    await request.app[ENGINE].delete(_search_id(request))
    return web.Response(status=204)


async def request_count(request: web.Request) -> web.Response:
    """How many requests these options would make, for the summary before saving."""
    body = await _json(request)
    return web.json_response(count_requests(body.get("options") or {}).as_dict())


def create_app(engine: Engine) -> web.Application:
    app = web.Application()
    app[ENGINE] = engine
    app.add_routes(
        [
            web.get("/api/info", info),
            web.post("/api/requests", request_count),
            web.get("/api/searches/{search_id}", get_search),
            web.put("/api/searches/{search_id}", put_search),
            web.delete("/api/searches/{search_id}", delete_search),
        ]
    )

    async def close(app: web.Application) -> None:
        await app[ENGINE].close()

    app.on_shutdown.append(close)
    return app
