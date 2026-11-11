"""The searches and what they found, as JSON files in the data folder."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any

# Home Assistant's entry ids are ULIDs: no dots or slashes can lead out of the folder.
SEARCH_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def valid_id(search_id: str) -> bool:
    return bool(SEARCH_ID_RE.match(search_id))


class Store:
    """searches/<id>/config.json is what a client asked for, state.json what the sources found."""

    def __init__(self, data_dir: Path) -> None:
        self._root = data_dir / "searches"

    def _folder(self, search_id: str) -> Path:
        if not valid_id(search_id):
            raise ValueError(f"invalid search id: {search_id!r}")
        return self._root / search_id

    async def load_config(self, search_id: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._read, self._folder(search_id) / "config.json")

    async def save_config(self, search_id: str, config: dict[str, Any]) -> None:
        await asyncio.to_thread(self._write, self._folder(search_id) / "config.json", config)

    async def load_state(self, search_id: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._read, self._folder(search_id) / "state.json")

    async def save_state(self, search_id: str, state: dict[str, Any]) -> None:
        await asyncio.to_thread(self._write, self._folder(search_id) / "state.json", state)

    async def delete(self, search_id: str) -> None:
        await asyncio.to_thread(shutil.rmtree, self._folder(search_id), True)

    @staticmethod
    def _read(path: Path) -> dict[str, Any] | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            # A file that is not JSON is as good as no file.
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _write(path: Path, data: dict[str, Any]) -> None:
        # A new file renamed over the old one: a stop in the middle never leaves half a file.
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, path)
