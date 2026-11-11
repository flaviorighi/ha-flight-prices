"""Where the prices come from."""

from __future__ import annotations


class SourceError(Exception):
    """A search failed; the next one may work."""


class SourceBlocked(SourceError):
    """The source refused to answer: stop searching it until the next round."""


def site_locale(language: str) -> tuple[str, str]:
    """Country and language in the airlines' links, from the language of Home Assistant."""
    language = language.split("-")[0].lower()
    if language in ("it", "de", "es", "fr", "pl", "pt", "nl"):
        return language, language
    return "gb", "en"
