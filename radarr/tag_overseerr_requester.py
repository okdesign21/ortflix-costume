#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Radarr Custom Script: On import/upgrade, tag the movie in Radarr with who
# requested it in Overseerr.
#
# Replaces: tautulli/scripts/tag_radarr_recently_added.py
# Advantage: fires at import (before Plex even sees the file), not after.
#
# Radarr → Settings → Connect → Custom Script
#   On Import: ✓   On Upgrade: ✓
#
# Env vars (set in docker-compose or Radarr container env):
#   RADARR_API_KEY       (required)
#   RADARR_URL           (optional; default: http://radarr:7878)
#   OVERSEERR_API_KEY    or SEERR_API_KEY  (required)
#   OVERSEERR_URL        or SEERR_URL      (optional; default: http://seerr:5055)
#
# Radarr injects these env vars automatically on each event:
#   radarr_eventtype       — "Download", "Upgrade", "Test", etc.
#   radarr_movie_tmdbid    — TMDb ID
#   radarr_movie_imdbid    — IMDb ID
#   radarr_movie_title     — Movie title
#   radarr_movie_year      — Release year

import os
import sys
from typing import Optional

import requests

from radarr_utils import (
    _env,
    fail,
    _clean_username,
    radarr_base_url,
    radarr_session,
    overseerr_base_url,
    overseerr_api_key,
    overseerr_session,
    find_movie,
    ensure_tag,
    add_tags_to_movie,
)


# ── Overseerr helpers ─────────────────────────────────────────────────────────

def _matches_media(req: dict, tmdb_id=None, imdb_id=None, title=None, year=None) -> bool:
    media = req.get("media") or {}
    if tmdb_id and str(media.get("tmdbId")) == str(tmdb_id):
        return True
    if imdb_id:
        if str(media.get("imdbId", "")).lower() == str(imdb_id).lower():
            return True
    if title:
        if str(media.get("title", "")).lower() == str(title).lower():
            if year is None or str(media.get("year")) == str(year):
                return True
    return False


def find_overseerr_request(
    s: requests.Session,
    base: str,
    tmdb_id=None,
    imdb_id=None,
    title=None,
    year=None,
) -> Optional[dict]:
    params = {"take": 100, "skip": 0, "filter": "approved", "sort": "added"}
    r = s.get(f"{base.rstrip('/')}/api/v1/request", params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    results = (data.get("results") if isinstance(data, dict) else data) or []
    for req in results:
        if _matches_media(req, tmdb_id=tmdb_id, imdb_id=imdb_id, title=title, year=year):
            return req
    return None


def requester_tag(user: Optional[dict]) -> str:
    if not user:
        return "unknown-requested"
    for key in ("displayName", "username"):
        val = user.get(key)
        if val:
            cleaned = _clean_username(val)
            if cleaned:
                return f"{cleaned}-requested"
    email = user.get("email")
    if email and "@" in email:
        cleaned = _clean_username(email.split("@")[0])
        if cleaned:
            return f"{cleaned}-requested"
    return "unknown-requested"


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    event = os.environ.get("radarr_eventtype", "")

    if event == "Test":
        print("[tag_overseerr_requester] Test event received — script is working.")
        sys.exit(0)

    if event not in ("Download", "Upgrade"):
        print(f"[tag_overseerr_requester] Skipping event type: {event!r}")
        sys.exit(0)

    tmdb_id = os.environ.get("radarr_movie_tmdbid")
    imdb_id = os.environ.get("radarr_movie_imdbid")
    title   = os.environ.get("radarr_movie_title")
    year    = os.environ.get("radarr_movie_year")

    RADARR_URL      = radarr_base_url()
    RADARR_API_KEY  = _env("RADARR_API_KEY", required=True)
    OVERSEERR_URL   = overseerr_base_url()
    OVERSEERR_KEY   = overseerr_api_key()

    r_session = radarr_session(RADARR_API_KEY)
    o_session = overseerr_session(OVERSEERR_KEY)

    try:
        movie = find_movie(r_session, RADARR_URL,
                           tmdb_id=tmdb_id, imdb_id=imdb_id, title=title, year=year)
    except Exception as e:
        fail(f"Radarr lookup failed: {e}")

    if not movie:
        fail(f"No matching movie in Radarr "
             f"(tmdb={tmdb_id!r}, imdb={imdb_id!r}, title={title!r}, year={year!r})")

    movie_id = movie.get("id")
    if not movie_id:
        fail("Matched Radarr movie missing 'id'.")

    try:
        req = find_overseerr_request(o_session, OVERSEERR_URL,
                                     tmdb_id=tmdb_id, imdb_id=imdb_id, title=title, year=year)
    except Exception as e:
        fail(f"Overseerr lookup failed: {e}")

    user      = req.get("requestedBy") if req else None
    tag_label = requester_tag(user)

    try:
        tag_id      = ensure_tag(r_session, RADARR_URL, tag_label)
        overseer_id = ensure_tag(r_session, RADARR_URL, "overseer")
        add_tags_to_movie(r_session, RADARR_URL, int(movie_id), [tag_id, overseer_id])
    except Exception as e:
        fail(f"Applying tags failed: {e}")

    requester_display = next(
        (user[k] for k in ("displayName", "username", "email") if user and user.get(k)), "unknown"
    ) if user else "unknown"

    print(
        f"[Radarr] Tagged '{movie.get('title')}' ({movie.get('year')}) "
        f"with ['{tag_label}', 'overseer'] "
        f"(id={movie_id}, requester={requester_display})"
    )


if __name__ == "__main__":
    main()
