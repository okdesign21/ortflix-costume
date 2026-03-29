#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Shared utilities for Radarr custom scripts.
# Mirrors the relevant subset of tautulli/scripts/tautulli_utils.py
# for use in the Radarr container (which can't import from the Tautulli container).

import os
import sys
from typing import Optional

import requests


# ── Common helpers ────────────────────────────────────────────────────────────

def _env(name, required=False, default=None):
    """Get environment variable; exit if required but missing."""
    v = os.getenv(name, default)
    if required and not v:
        print(f"[ERROR] Missing env var: {name}", file=sys.stderr)
        sys.exit(2)
    return v


def fail(msg, code=1):
    """Print error to stderr and exit."""
    print(f"[ERROR] {msg}", file=sys.stderr)
    sys.exit(code)


def _clean_username(name: Optional[str]) -> Optional[str]:
    """Slugify a username to ASCII alphanumeric + hyphens (Radarr tag requirement).
    Returns None if no valid ASCII characters remain (e.g., Japanese display names).
    """
    if not name:
        return None
    cleaned = "".join(
        ch.lower() if (ch.isascii() and ch.isalnum()) else "-" for ch in str(name)
    )
    cleaned = cleaned.strip("-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    if not cleaned or not any(ch.isascii() and ch.isalnum() for ch in cleaned):
        return None
    return cleaned


# ── URL builders ──────────────────────────────────────────────────────────────

def radarr_base_url() -> str:
    url = os.getenv("RADARR_URL")
    if url:
        return url.rstrip("/")
    port = os.getenv("RADARR_PORT", "7878")
    return f"http://radarr:{port}"


def overseerr_base_url() -> str:
    url = os.getenv("OVERSEERR_URL") or os.getenv("SEERR_URL")
    if url:
        return url.rstrip("/")
    host = os.getenv("OVERSEERR_HOST") or os.getenv("SEERR_HOST") or "seerr"
    port = os.getenv("OVERSEERR_PORT") or os.getenv("SEERR_PORT") or "5055"
    return f"http://{host}:{port}"


# ── Session factories ─────────────────────────────────────────────────────────

def radarr_session(api_key: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Accept": "application/json", "X-Api-Key": api_key})
    return s


def overseerr_api_key() -> str:
    key = os.getenv("OVERSEERR_API_KEY") or os.getenv("SEERR_API_KEY")
    if not key:
        fail("Missing OVERSEERR_API_KEY or SEERR_API_KEY in environment")
    return key


def overseerr_session(api_key: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Accept": "application/json", "X-Api-Key": api_key})
    return s


# ── Radarr API helpers ────────────────────────────────────────────────────────

def find_movie(
    s: requests.Session,
    base: str,
    tmdb_id=None,
    imdb_id=None,
    title=None,
    year=None,
) -> dict | None:
    """Find a movie in Radarr by tmdbId → imdbId → title+year."""
    base_url = base.rstrip("/")

    def _first(data):
        if isinstance(data, list):
            return data[0] if data else None
        return data if isinstance(data, dict) else None

    # Fast path: server-side filter
    if tmdb_id and str(tmdb_id).isdigit():
        try:
            r = s.get(f"{base_url}/api/v3/movie", params={"tmdbId": str(tmdb_id)}, timeout=10)
            if r.status_code == 200:
                data = _first(r.json())
                if data and str(data.get("tmdbId")) == str(tmdb_id):
                    return data
        except Exception:
            pass

    if imdb_id:
        try:
            r = s.get(f"{base_url}/api/v3/movie", params={"imdbId": str(imdb_id)}, timeout=10)
            if r.status_code == 200:
                data = _first(r.json())
                if data and str(data.get("imdbId", "")).lower() == str(imdb_id).lower():
                    return data
        except Exception:
            pass

    # Full list fallback
    r = s.get(f"{base_url}/api/v3/movie", timeout=20)
    r.raise_for_status()
    movies = r.json()

    if tmdb_id and str(tmdb_id).isdigit():
        for m in movies:
            if str(m.get("tmdbId")) == str(tmdb_id):
                return m
    if imdb_id:
        iid = str(imdb_id).lower()
        for m in movies:
            if str(m.get("imdbId", "")).lower() == iid:
                return m
    if title:
        tl = str(title).lower()
        candidates = [m for m in movies if str(m.get("title", "")).lower() == tl]
        if year:
            for m in candidates:
                if str(m.get("year")) == str(year):
                    return m
        if len(candidates) == 1:
            return candidates[0]

    return None


def ensure_tag(s: requests.Session, base: str, label: str) -> int:
    """Return tag ID by label (case-insensitive); create if missing."""
    r = s.get(f"{base.rstrip('/')}/api/v3/tag", timeout=15)
    r.raise_for_status()
    for t in r.json():
        if str(t.get("label", "")).lower() == label.lower():
            return int(t["id"])
    cr = s.post(f"{base.rstrip('/')}/api/v3/tag", json={"label": label}, timeout=15)
    if cr.status_code not in (200, 201):
        fail(f"Creating tag '{label}' failed: HTTP {cr.status_code} {cr.text}")
    return int(cr.json()["id"])


def add_tags_to_movie(s: requests.Session, base: str, movie_id: int, tag_ids: list[int]) -> None:
    """Add tags to a movie via the Radarr bulk editor."""
    payload = {"movieIds": [movie_id], "tags": list(set(tag_ids)), "applyTags": "add"}
    r = s.put(f"{base.rstrip('/')}/api/v3/movie/editor", json=payload, timeout=25)
    if r.status_code not in (200, 202):
        fail(f"Tagging failed: HTTP {r.status_code} - {r.text}")


# ── Telegram ─────────────────────────────────────────────────────────────────

def telegram_post(text: str) -> None:
    """Send a message to the Telegram bot.

    Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from env
    (injected from Docker secrets by the container entrypoint).
    Silently skips if either is missing.
    """
    token   = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
        if not r.ok:
            print(f"[WARN] Telegram send failed: {r.status_code} - {r.text}", file=sys.stderr)
    except Exception as e:
        print(f"[WARN] Telegram exception: {e}", file=sys.stderr)
