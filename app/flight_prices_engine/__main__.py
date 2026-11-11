"""Start the engine: python -m flight_prices_engine."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
from pathlib import Path
import signal
import socket

import aiohttp
from aiohttp import web

from . import __version__
from .const import DEFAULT_PORT
from .server import INGRESS_IP, Engine, create_app
from .store import Store

_LOGGER = logging.getLogger("flight_prices_engine")

# Inside Home Assistant OS the Supervisor answers here, with the token it gives the app.
SUPERVISOR_URL = "http://supervisor"
DOMAIN = "flight_prices"


def _options(data_dir: Path) -> dict[str, object]:
    """The app's options, written by the Supervisor; none when run with plain Docker."""
    try:
        return json.loads((data_dir / "options.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


async def _announce(session: aiohttp.ClientSession, port: int, password: str | None) -> None:
    """Tell Home Assistant where the app is: the integration offers itself as discovered."""
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return
    # The Supervisor names the container after the app, and Home Assistant resolves that name.
    config: dict[str, object] = {"host": socket.gethostname(), "port": port}
    if password:
        # Only Home Assistant reads discovery messages: the integration needs it like any other client.
        config["password"] = password
    try:
        async with session.post(
            f"{SUPERVISOR_URL}/discovery",
            json={"service": DOMAIN, "config": config},
            headers={"Authorization": f"Bearer {token}"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as response:
            response.raise_for_status()
        _LOGGER.info("Announced to Home Assistant at %s:%s", config["host"], port)
    except aiohttp.ClientError as err:
        _LOGGER.warning("Could not announce the app to Home Assistant: %s", err)


async def main(data_dir: Path, host: str, port: int, password: str | None = None) -> None:
    # Inside Home Assistant OS, the page opened from the sidebar comes through the Supervisor's ingress proxy.
    trusted = INGRESS_IP if os.environ.get("SUPERVISOR_TOKEN") else None
    async with aiohttp.ClientSession() as session:
        engine = Engine(Store(data_dir), session)
        await engine.load()
        runner = web.AppRunner(create_app(engine, password, trusted), access_log=None)
        await runner.setup()
        await web.TCPSite(runner, host, port).start()
        _LOGGER.info(
            "Flight Prices %s listening on %s:%s, %s",
            __version__,
            host,
            port,
            "with a password" if password else "without a password",
        )
        await _announce(session, port, password)

        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, stop.set)
        await stop.wait()
        _LOGGER.info("Stopping")
        # Closing the runner closes every search: a Google round saves what it found so far.
        await runner.cleanup()


def run() -> None:
    parser = argparse.ArgumentParser(prog="flight_prices_engine", description=__doc__)
    parser.add_argument("--data", type=Path, default=Path(os.environ.get("FLIGHT_PRICES_DATA", "/data")))
    parser.add_argument("--host", default=os.environ.get("FLIGHT_PRICES_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("FLIGHT_PRICES_PORT", DEFAULT_PORT)))
    args = parser.parse_args()
    options = _options(args.data)
    level = str(options.get("log_level") or os.environ.get("FLIGHT_PRICES_LOG_LEVEL", "info"))
    password = str(options.get("password") or os.environ.get("FLIGHT_PRICES_PASSWORD") or "") or None
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(main(args.data, args.host, args.port, password))


if __name__ == "__main__":
    run()
