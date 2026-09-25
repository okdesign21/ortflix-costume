"""Authoritative Plex title index — the new source of truth for asset matching.

Instead of guessing a target folder name purely from string transforms
(``normalize_name``'s old colon/asterisk/space rules) plus an ever-growing
``exception_mappings.json``, this module builds an index of the *actual*
titles Plex/Kometa expects, taken directly from the Plex server:

  - ``movies_shows``  — every movie/show title (``Title`` or ``Title (Year)``)
  - ``collections``   — every collection title, per library
  - ``people``        — every actor/director/writer/producer name seen
  - ``genres``         — every genre value seen
  - ``studios``        — every studio/network value seen (→ Companies category)

Matching against this index (see ``matcher.py``) turns "reconstruct the
correct name" into "find the closest known-good name" — a much smaller and
more reliable problem than open-ended string normalization.

Credentials
-----------
Resolved in this order (first match wins), mirroring the retired
``scripts/check_plex_titles.py`` helper:

  1. ``KOMETA_PLEXURL`` / ``KOMETA_PLEXTOKEN`` env vars (Kometa's own Docker
     naming — see ``ortflix/compose/docker-compose-onelayer.yml``).
  2. If ``KOMETA_PLEXURL`` is unset, fall back to
     ``http://{ORTFLIX_SYNC_HOST}:{KOMETA_PLEX_PORT or 32400}``.

Values may be literal strings, a file path, or ``sudo cat /path/to/secret``
(resolved on this machine).

Caching
-------
The built index is a plain JSON snapshot (``plex_index_cache.json`` by
default) with a ``snapshot_at`` timestamp, so runs don't need live Plex
connectivity every time. Use ``--refresh-plex-index`` (see
``organize_assets.py``) to force a rebuild, or let it auto-refresh once the
cache is older than ``PLEX_INDEX_MAX_AGE_HOURS`` (default 24h).
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

DEFAULT_LIBRARIES = ("Films", "TV Programmes")
DEFAULT_MAX_AGE_HOURS = 24.0

_INDEX_NAMES = ("movies_shows", "collections", "people", "genres", "studios")


def normalize_key(name: str) -> str:
    """Loose comparison key: casefold, strip accents/punctuation, collapse spaces.

    Used only for *matching* — never for the output folder name (the
    canonical Plex title is always used verbatim as the destination name).
    """
    if not name:
        return ""
    n = unicodedata.normalize("NFKD", name)
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = n.casefold()
    n = re.sub(r"[^a-z0-9]+", " ", n)
    return re.sub(r"\s+", " ", n).strip()


# ---------------------------------------------------------------------------
# Credential resolution (mirrors the retired scripts/check_plex_titles.py)
# ---------------------------------------------------------------------------


def _try_resolve_secret(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    m = re.match(r"^(?:sudo\s+)?cat\s+(.+)$", s, re.IGNORECASE)
    if m:
        path_str = m.group(1).strip().strip('"').strip("'")
        path = Path(path_str).expanduser()
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()
        try:
            r = subprocess.run(
                ["sudo", "cat", str(path)], capture_output=True, text=True, timeout=60
            )
            if r.returncode == 0:
                return r.stdout.strip()
        except (FileNotFoundError, subprocess.SubprocessError, TimeoutError):
            pass
        return None
    expanded = Path(s).expanduser()
    if expanded.is_file():
        return expanded.read_text(encoding="utf-8").strip()
    return s


def load_plex_credentials() -> tuple[Optional[str], Optional[str]]:
    """Return ``(url, token)``, or ``(None, None)`` components that are unset."""
    url = _try_resolve_secret(os.getenv("KOMETA_PLEXURL"))
    if not url:
        host = os.getenv("ORTFLIX_SYNC_HOST", "").strip()
        if host:
            port = os.getenv("KOMETA_PLEX_PORT", "32400").strip() or "32400"
            url = f"http://{host}:{port}"
    token = _try_resolve_secret(os.getenv("KOMETA_PLEXTOKEN"))
    return url, token


# ---------------------------------------------------------------------------
# Index data structure
# ---------------------------------------------------------------------------


@dataclass
class PlexIndex:
    """Normalized-key → canonical-name lookups, one dict per asset category."""

    movies_shows: dict[str, str] = field(default_factory=dict)
    collections: dict[str, str] = field(default_factory=dict)
    people: dict[str, str] = field(default_factory=dict)
    genres: dict[str, str] = field(default_factory=dict)
    studios: dict[str, str] = field(default_factory=dict)
    snapshot_at: float = 0.0
    libraries: tuple[str, ...] = ()

    def get(self, category: str) -> dict[str, str]:
        return getattr(self, category, {})

    def is_empty(self) -> bool:
        return not any(self.get(name) for name in _INDEX_NAMES)

    def age_hours(self) -> float:
        if not self.snapshot_at:
            return float("inf")
        return (time.time() - self.snapshot_at) / 3600.0

    # -- (de)serialization ---------------------------------------------------

    def to_json(self) -> str:
        payload = {
            "snapshot_at": self.snapshot_at,
            "libraries": list(self.libraries),
            **{name: self.get(name) for name in _INDEX_NAMES},
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "PlexIndex":
        data = json.loads(text)
        return cls(
            movies_shows=data.get("movies_shows", {}),
            collections=data.get("collections", {}),
            people=data.get("people", {}),
            genres=data.get("genres", {}),
            studios=data.get("studios", {}),
            snapshot_at=data.get("snapshot_at", 0.0),
            libraries=tuple(data.get("libraries", [])),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> Optional["PlexIndex"]:
        if not path.is_file():
            return None
        try:
            return cls.from_json(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load Plex index cache %s: %s", path, exc)
            return None


# ---------------------------------------------------------------------------
# Building the index from a live Plex server
# ---------------------------------------------------------------------------


def _canonical_item_name(item: Any) -> str:
    """Return the folder name Kometa expects for a movie/show item.

    Movies always carry a disambiguating year; shows only do when Plex's own
    title doesn't already make the item unique across the library (Plex show
    titles are typically bare, e.g. "Friends", matching Kometa's asset
    matching by exact title).
    """
    title = getattr(item, "title", "") or ""
    year = getattr(item, "year", None)
    item_type = getattr(item, "type", "movie")
    if item_type == "show":
        return title
    return f"{title} ({year})" if year else title


def _iter_people(item: Any) -> Iterable[str]:
    for attr in ("roles", "directors", "writers", "producers"):
        for person in getattr(item, attr, None) or []:
            tag = getattr(person, "tag", None)
            if tag:
                yield tag


def build_index(plex: Any, libraries: Iterable[str] = DEFAULT_LIBRARIES) -> PlexIndex:
    """Query a connected ``PlexServer`` and build a fresh :class:`PlexIndex`."""
    index = PlexIndex(snapshot_at=time.time(), libraries=tuple(libraries))

    sections_by_title = {s.title: s for s in plex.library.sections()}
    resolved_libraries = []
    for lib_name in libraries:
        section = sections_by_title.get(lib_name)
        if section is None:
            logger.warning("Plex library not found, skipping: %s", lib_name)
            continue
        resolved_libraries.append(lib_name)

        for item in section.all():
            canonical = _canonical_item_name(item)
            if canonical:
                index.movies_shows[normalize_key(canonical)] = canonical

            for genre_tag in getattr(item, "genres", None) or []:
                g = getattr(genre_tag, "tag", None)
                if g:
                    index.genres[normalize_key(g)] = g

            studio = getattr(item, "studio", None)
            if studio:
                index.studios[normalize_key(studio)] = studio

            for person_name in _iter_people(item):
                index.people[normalize_key(person_name)] = person_name

        for collection in section.collections():
            title = getattr(collection, "title", None)
            if title:
                index.collections[normalize_key(title)] = title

    index.libraries = tuple(resolved_libraries)
    logger.info(
        "Plex index built: %d movies/shows, %d collections, %d people, %d genres, %d studios",
        len(index.movies_shows),
        len(index.collections),
        len(index.people),
        len(index.genres),
        len(index.studios),
    )
    return index


def connect_plex(url: str, token: str) -> Any:
    """Connect to a Plex server, raising a clear error if ``plexapi`` is missing."""
    try:
        from plexapi.server import PlexServer
    except ImportError as exc:  # pragma: no cover - exercised via integration only
        raise RuntimeError(
            "plexapi is not installed; run `pip install plexapi` to enable "
            "Plex-based asset matching."
        ) from exc
    return PlexServer(url, token)


def build_or_load_index(
    cache_path: Path,
    *,
    libraries: Iterable[str] = DEFAULT_LIBRARIES,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
    force_refresh: bool = False,
) -> Optional[PlexIndex]:
    """Return a fresh-enough :class:`PlexIndex`, refreshing from Plex if needed.

    Returns ``None`` (never raises) when Plex is unreachable/unconfigured and
    no usable cache exists — callers should degrade gracefully (fall back to
    the legacy normalization rules) rather than fail the whole run.
    """
    cached = None if force_refresh else PlexIndex.load(cache_path)
    if cached is not None and not cached.is_empty() and cached.age_hours() <= max_age_hours:
        logger.info(
            "Using cached Plex index (%.1fh old): %s", cached.age_hours(), cache_path
        )
        return cached

    url, token = load_plex_credentials()
    if not url or not token:
        if cached is not None:
            logger.warning(
                "Plex credentials not set; using stale cache (%.1fh old)",
                cached.age_hours(),
            )
            return cached
        logger.warning(
            "Plex credentials not set (KOMETA_PLEXURL/KOMETA_PLEXTOKEN); "
            "Plex-based matching disabled for this run."
        )
        return None

    try:
        plex = connect_plex(url, token)
        fresh = build_index(plex, libraries=libraries)
        fresh.save(cache_path)
        return fresh
    except Exception as exc:  # noqa: BLE001 - degrade gracefully, never crash organize
        logger.warning("Failed to refresh Plex index (%s): %s", url, exc)
        if cached is not None:
            logger.warning("Using stale cache instead (%.1fh old)", cached.age_hours())
            return cached
        return None
