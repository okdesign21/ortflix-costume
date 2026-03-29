#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Shared utilities for Tautulli scripts.
# Provides common helpers for Radarr, Sonarr, Overseerr, and Discord integrations.

import os
import sys
from typing import Optional

import requests


# ====== Common Helpers ======
def _env(name, required=False, default=None):
    """Get environment variable, exit if required but missing."""
    v = os.getenv(name, default)
    if required and not v:
        print(f"[ERROR] Missing env var: {name}", file=sys.stderr)
        sys.exit(2)
    return v


def fail(msg, code=1):
    """Print error and exit."""
    print(f"[ERROR] {msg}", file=sys.stderr)
    sys.exit(code)


def _clean_username(name: Optional[str]) -> Optional[str]:
    """Slugify username for tag labels: ASCII alphanumeric + hyphens only (Radarr/Sonarr requirement).
    Returns None if username contains non-ASCII characters or no alphanumeric characters.
    """
    if not name:
        return None
    # Only keep ASCII letters, digits, and replace others with hyphens
    cleaned = "".join(
        ch.lower() if (ch.isascii() and ch.isalnum()) else "-" for ch in str(name)
    )
    cleaned = cleaned.strip("-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    # If no valid ASCII alphanumeric chars remain, return None for fallback
    if not cleaned or not any(ch.isascii() and ch.isalnum() for ch in cleaned):
        return None
    return cleaned


# ====== Base URL Helpers ======
def radarr_base_url() -> str:
    """Get Radarr base URL from env or radarr:7878."""
    url = os.getenv("RADARR_URL")
    if url:
        return url.rstrip("/")
    port = os.getenv("RADARR_PORT", "7878")
    return f"http://radarr:{port}".rstrip("/")


def sonarr_base_url() -> str:
    """Get Sonarr base URL from env or sonarr:8989."""
    url = os.getenv("SONARR_URL")
    if url:
        return url.rstrip("/")
    port = os.getenv("SONARR_PORT", "8989")
    return f"http://sonarr:{port}".rstrip("/")


def overseerr_base_url() -> str:
    """Get Seerr/Overseerr base URL from env.

    Resolution order:
    1) OVERSEERR_URL
    2) SEERR_URL
    3) http://<OVERSEERR_HOST|SEERR_HOST|seerr>:<OVERSEERR_PORT|SEERR_PORT|5055>
    """
    url = os.getenv("OVERSEERR_URL") or os.getenv("SEERR_URL")
    if url:
        return url.rstrip("/")

    host = os.getenv("OVERSEERR_HOST") or os.getenv("SEERR_HOST") or "seerr"
    port = os.getenv("OVERSEERR_PORT") or os.getenv("SEERR_PORT") or "5055"
    return f"http://{host}:{port}".rstrip("/")


# ====== Session Factories ======
def radarr_session(api_key: str) -> requests.Session:
    """Create Radarr API session with key."""
    s = requests.Session()
    s.headers.update({"Accept": "application/json", "X-Api-Key": api_key})
    return s


def sonarr_session(api_key: str) -> requests.Session:
    """Create Sonarr API session with key."""
    s = requests.Session()
    s.headers.update({"Accept": "application/json", "X-Api-Key": api_key})
    return s


def overseerr_api_key() -> str:
    """Get Overseerr API key from env.

    Resolution order:
    1) OVERSEERR_API_KEY
    2) SEERR_API_KEY
    """
    key = os.getenv("OVERSEERR_API_KEY") or os.getenv("SEERR_API_KEY")
    if not key:
        fail("Missing OVERSEERR_API_KEY or SEERR_API_KEY in environment")
    return key


def overseerr_session(api_key: str) -> requests.Session:
    """Create Overseerr API session with key."""
    s = requests.Session()
    s.headers.update({"Accept": "application/json", "X-Api-Key": api_key})
    return s


# ====== Radarr/Sonarr Common ======
def ensure_tag(s: requests.Session, base: str, label: str) -> int:
    """Return tag id by label (case-insensitive); create if missing."""
    r = s.get(f"{base.rstrip('/')}/api/v3/tag", timeout=15)
    r.raise_for_status()
    for t in r.json():
        if str(t.get("label", "")).strip().lower() == label.strip().lower():
            return int(t["id"])
    cr = s.post(f"{base.rstrip('/')}/api/v3/tag", json={"label": label}, timeout=15)
    if cr.status_code not in (200, 201):
        fail(f"Creating tag '{label}' failed: HTTP {cr.status_code} {cr.text}")
    return int(cr.json()["id"])


# ====== Radarr ======
def find_movie(
    s: requests.Session,
    base: str,
    tmdb_id=None,
    imdb_id=None,
    title=None,
    year=None,
) -> dict | None:
    """Find movie in Radarr by tmdbId → imdbId → exact title (+year)."""
    base_url = base.rstrip("/")

    def _first_or_none(data):
        if isinstance(data, list):
            return data[0] if data else None
        if isinstance(data, dict):
            return data
        return None

    # Fast path: server-side filter by tmdbId / imdbId (if supported)
    if tmdb_id and str(tmdb_id).isdigit():
        try:
            r = s.get(
                f"{base_url}/api/v3/movie",
                params={"tmdbId": str(tmdb_id)},
                timeout=10,
            )
            if r.status_code == 200:
                data = _first_or_none(r.json())
                if data and str(data.get("tmdbId")) == str(tmdb_id):
                    return data
        except Exception:  # nosec - intentionally suppress API errors during fast-path lookup
            pass

    if imdb_id:
        try:
            r = s.get(
                f"{base_url}/api/v3/movie",
                params={"imdbId": str(imdb_id)},
                timeout=10,
            )
            if r.status_code == 200:
                data = _first_or_none(r.json())
                if (
                    data
                    and str(data.get("imdbId", "")).strip().lower()
                    == str(imdb_id).strip().lower()
                ):
                    return data
        except Exception:  # nosec - intentionally suppress API errors during fast-path lookup
            pass

    r = s.get(f"{base_url}/api/v3/movie", timeout=20)
    r.raise_for_status()
    movies = r.json()

    # TMDb first
    if tmdb_id and str(tmdb_id).isdigit():
        for m in movies:
            if str(m.get("tmdbId")) == str(tmdb_id):
                return m

    # IMDb fallback
    if imdb_id:
        iid = str(imdb_id).strip().lower()
        for m in movies:
            if str(m.get("imdbId", "")).strip().lower() == iid:
                return m

    # Title + year fallback
    if title:
        tl = str(title).strip().lower()
        candidates = [
            m for m in movies if str(m.get("title", "")).strip().lower() == tl
        ]
        if year:
            for m in candidates:
                if str(m.get("year")) == str(year):
                    return m
        if len(candidates) == 1:
            return candidates[0]

    return None


def add_tags_to_movie(
    s: requests.Session, base: str, movie_id: int, tag_ids: list[int]
) -> None:
    """Add tags to a movie using bulk editor."""
    payload = {"movieIds": [movie_id], "tags": list(set(tag_ids)), "applyTags": "add"}
    r = s.put(f"{base.rstrip('/')}/api/v3/movie/editor", json=payload, timeout=25)
    if r.status_code not in (200, 202):
        fail(f"Tagging failed: HTTP {r.status_code} - {r.text}")


# ====== Sonarr ======
def find_series(
    s: requests.Session,
    base: str,
    tvdb_id=None,
    imdb_id=None,
    title=None,
    year=None,
) -> dict | None:
    """Find series in Sonarr by tvdbId → imdbId → exact title (+year)."""
    r = s.get(f"{base.rstrip('/')}/api/v3/series", timeout=40)
    r.raise_for_status()
    series = r.json()

    if tvdb_id and str(tvdb_id).isdigit():
        for srs in series:
            if str(srs.get("tvdbId")) == str(tvdb_id):
                return srs

    if imdb_id:
        iid = str(imdb_id).strip().lower()
        for srs in series:
            if str(srs.get("imdbId", "")).strip().lower() == iid:
                return srs

    if title:
        tl = str(title).strip().lower()
        candidates = [
            srs for srs in series if str(srs.get("title", "")).strip().lower() == tl
        ]
        if year:
            for srs in candidates:
                if str(srs.get("year")) == str(year):
                    return srs
        if len(candidates) == 1:
            return candidates[0]

    return None


def add_tags_to_series(
    s: requests.Session, base: str, series_id: int, tag_ids: list[int]
) -> None:
    """Add tags to a series using bulk editor."""
    payload = {"seriesIds": [series_id], "tags": list(set(tag_ids)), "applyTags": "add"}
    r = s.put(f"{base.rstrip('/')}/api/v3/series/editor", json=payload, timeout=25)
    if r.status_code not in (200, 202):
        fail(f"Tagging failed: HTTP {r.status_code} - {r.text}")


# ====== Discord ======
def discord_post(content: str, webhook_url: str = None) -> None:
    """Post a message to Discord via webhook (optional)."""
    webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        return
    try:
        r = requests.post(webhook_url, json={"content": content}, timeout=10)
        if r.status_code != 204:
            print(
                f"[WARN] Discord send failed: {r.status_code} - {r.text}",
                file=sys.stderr,
            )
    except Exception as e:
        print(f"[WARN] Discord exception: {e}", file=sys.stderr)
