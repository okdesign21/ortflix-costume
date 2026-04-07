"""TMDb title resolver — last-resort canonical name lookup for movie/show assets.

Lookup order in normalize_name:
  1. exception_mappings.json  (exact, manual overrides)
  2. standard normalization rules  (colons, asterisks, double-spaces …)
  3. THIS module  (only when a year is present and none of the above matched)

Results are persisted in a local cache (``tmdb_cache.json`` next to
``exception_mappings.json``) so the API is only hit once per unknown title.

When TMDb returns a title that differs from the locally-normalized version, the
mapping is **automatically written back to exception_mappings.json** — future
runs will use the fast in-process lookup instead of a network call.

Configuration
-------------
Set ``TMDB_API_KEY`` (v3 key) in your environment or ``.env`` file::

    TMDB_API_KEY=your_key_here

If the env var is absent the resolver is disabled and normalize_name falls
back to the existing rules (no breakage, no network calls).
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Matches "Some Title (2003)" or "Some Title (2003) extra"
_YEAR_RE = re.compile(r"^(.+?)\s*\((\d{4})\)")

# Season/specials suffix to strip before lookup and reattach after
_SEASON_SUFFIX_RE = re.compile(r"(\s+-\s+(?:Season\s+\d+|Specials))\s*$", re.IGNORECASE)


class TmdbResolver:
    """Resolve movie/show titles via the TMDb v3 search API.

    Parameters
    ----------
    api_key:
        TMDb API v3 key.
    cache_path:
        Path to the JSON file used for persistent caching.  Created
        automatically when the first result is stored.
    exception_mappings_path:
        Path to ``exception_mappings.json``.  When *write_back* is True and a
        new mapping is discovered it is appended here so future runs skip the
        network call entirely.
    write_back:
        Automatically add confirmed TMDb corrections to exception_mappings.
    rate_limit_delay:
        Minimum seconds between outbound requests (TMDb free tier allows
        ~50 req/s; 0.1 s is a conservative default).
    """

    _BASE = "https://api.themoviedb.org/3"

    def __init__(
        self,
        api_key: str,
        cache_path: Optional[Path] = None,
        exception_mappings_path: Optional[Path] = None,
        write_back: bool = True,
        rate_limit_delay: float = 0.1,
    ) -> None:
        self.api_key = api_key
        self.cache_path = cache_path
        self.exception_mappings_path = exception_mappings_path
        self.write_back = write_back
        self.rate_limit_delay = rate_limit_delay
        self._cache: dict[str, str] = {}
        self._last_req: float = 0.0
        self._api_calls: int = 0

        if cache_path and cache_path.is_file():
            try:
                self._cache = json.loads(cache_path.read_text(encoding="utf-8"))
                logger.debug(
                    "TMDb cache: loaded %d entries from %s", len(self._cache), cache_path
                )
            except Exception as exc:
                logger.warning("Failed to load TMDb cache %s: %s", cache_path, exc)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_req
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self._last_req = time.monotonic()

    def _save_cache(self) -> None:
        if not self.cache_path:
            return
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(
                json.dumps(dict(sorted(self._cache.items())), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("Failed to save TMDb cache: %s", exc)

    def _write_back(self, source_name: str, canonical: str) -> None:
        """Append *source_name → canonical* to exception_mappings.json."""
        if not self.write_back or not self.exception_mappings_path:
            return
        try:
            mappings: dict[str, str] = {}
            if self.exception_mappings_path.is_file():
                mappings = json.loads(
                    self.exception_mappings_path.read_text(encoding="utf-8")
                )
            if source_name in mappings:
                return  # already present — don't overwrite manual entries
            mappings[source_name] = canonical
            self.exception_mappings_path.write_text(
                json.dumps(dict(sorted(mappings.items())), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info(
                "TMDb write-back → exception_mappings: %r -> %r", source_name, canonical
            )
        except Exception as exc:
            logger.warning("Failed to write back to exception_mappings: %s", exc)

    def _fetch(self, endpoint: str, params: dict) -> list[dict]:
        """GET *endpoint* with *params* and return the results list."""
        params["api_key"] = self.api_key
        params["language"] = "en-US"
        url = f"{self._BASE}/{endpoint}?{urllib.parse.urlencode(params)}"
        try:
            self._throttle()
            self._api_calls += 1
            with urllib.request.urlopen(url, timeout=8) as resp:
                return json.loads(resp.read().decode("utf-8")).get("results", [])
        except Exception as exc:
            logger.debug("TMDb fetch failed (%s): %s", url, exc)
            return []

    def _best_title(
        self,
        results: list[dict],
        title_field: str,
        date_field: str,
        year: Optional[int],
    ) -> Optional[str]:
        """Return the title of the best-matching result, or None."""
        for item in results[:5]:
            res_title = item.get(title_field, "")
            res_date = item.get(date_field, "") or ""
            res_year = int(res_date[:4]) if len(res_date) >= 4 else None
            if year is None or res_year is None or abs(res_year - year) <= 1:
                return res_title
        return None

    def _search(self, title: str, year: Optional[int]) -> Optional[str]:
        """Query TMDb (movie then TV) and return the official title, or None."""
        # Movie search
        params: dict = {"query": title, "include_adult": "false"}
        if year:
            params["year"] = year
        results = self._fetch("search/movie", params)
        found = self._best_title(results, "title", "release_date", year)
        if found:
            return found

        # TV search
        params2: dict = {"query": title}
        if year:
            params2["first_air_date_year"] = year
        results2 = self._fetch("search/tv", params2)
        return self._best_title(results2, "name", "first_air_date", year)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(self, name: str) -> Optional[str]:
        """Return the TMDb-canonical folder name for *name*, or ``None``.

        *name* should be the **pre-normalization** stem, e.g.
        ``"Petes Dragon (1977)"``.  Returns ``None`` when the lookup finds
        nothing new (network error, no match, or TMDb agrees with *name*).

        Side effects
        ------------
        - Persists the result (hit or miss) in the local cache.
        - When a correction is found, writes it back to exception_mappings.
        """
        # 1. Cache hit
        if name in self._cache:
            cached = self._cache[name]
            # Empty string means "looked up before, no improvement found"
            return cached if cached else None

        # 2. Strip season/specials suffix before lookup, reattach after
        #    e.g. "Star Trek Discovery (2017) - Season 1" → lookup "Star Trek Discovery (2017)",
        #    then return "Star Trek: Discovery (2017) - Season 1"
        season_suffix = ""
        lookup_name = name
        sm = _SEASON_SUFFIX_RE.search(name)
        if sm:
            season_suffix = sm.group(1)
            lookup_name = name[: sm.start()]

        # 3. Extract title + year
        m = _YEAR_RE.match(lookup_name)
        if not m:
            # No year → not a movie/show item; skip TMDb
            self._cache[name] = ""
            return None

        raw_title = m.group(1).strip()
        year = int(m.group(2))

        # 4. Query TMDb
        official = self._search(raw_title, year)

        if official:
            canonical = f"{official} ({year}){season_suffix}"
        else:
            canonical = None

        # 5. Persist cache (keyed on the original full name including season suffix)
        self._cache[name] = canonical or ""
        self._save_cache()

        # 6. Write back if this is a genuine correction
        if canonical and canonical != name:
            self._write_back(name, canonical)
            return canonical

        return None

    @property
    def api_call_count(self) -> int:
        """Number of live API calls made this session (cache hits excluded)."""
        return self._api_calls


def build_resolver(
    exception_mappings_path: Path,
) -> Optional[TmdbResolver]:
    """Create a TmdbResolver from env, or return None if TMDB_API_KEY is unset."""
    import os

    key = os.getenv("TMDB_API_KEY", "").strip()
    if not key:
        return None

    cache_path = exception_mappings_path.parent / "tmdb_cache.json"
    resolver = TmdbResolver(
        api_key=key,
        cache_path=cache_path,
        exception_mappings_path=exception_mappings_path,
        write_back=True,
    )
    logger.info("TMDb resolver enabled (cache: %s)", cache_path)
    return resolver
