#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# DEPRECATED: Superseded by radarr/scripts/tag_overseerr_requester.py
# That version runs as a Radarr Custom Script (fires at import, before Plex sees the file).
# Keep this file only as a fallback if the Radarr script is unavailable.
#
# Tautulli Script: On Plex "Recently Added", tag the movie in Radarr with who requested it in Overseerr.

# - Adds tags: "requested-by-{overseerr_user}" (slugified) and "overseerr-request".
# - Looks up the matching Overseerr request via tmdbId → imdbId → title+year.

# Tautulli Script Arguments (recently added):
#   --themoviedb_id {themoviedb_id} --imdb_id {imdb_id} --title "{title}" --year {year}

# Env on Tautulli host/container:
#   RADARR_API_KEY
#   RADARR_URL   (optional; defaults to http://localhost:<RADARR_PORT|7878>)
#   RADARR_PORT  (optional; defaults to 7878)
#   OVERSEERR_API_KEY
#   OVERSEERR_URL   (optional; defaults to http://localhost:<OVERSEERR_PORT|5055>)
#   OVERSEERR_PORT  (optional; defaults to 5055)

import argparse
from typing import Optional

from tautulli_utils import (
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

import requests


# ====== Overseerr logic ======
def requester_tag(user: Optional[dict]) -> str:
    """Format the requester tag from user object, with email fallback for invalid usernames."""
    if not user:
        return "unknown-requested"

    # Try display name and username first
    for key in ("displayName", "username"):
        val = user.get(key)
        if val:
            cleaned = _clean_username(val)
            if cleaned:
                return f"{cleaned}-requested"

    # Fallback to email prefix if username has no valid chars (e.g., Japanese)
    email = user.get("email")
    if email and "@" in email:
        email_prefix = email.split("@")[0]
        cleaned = _clean_username(email_prefix)
        if cleaned:
            return f"{cleaned}-requested"

    return "unknown-requested"


def extract_requester(req: dict) -> Optional[dict]:
    """Extract requester user object from Overseerr request."""
    return req.get("requestedBy") if req else None


def _matches_media(
    req: dict, tmdb_id=None, imdb_id=None, title=None, year=None
) -> bool:
    """Check if Overseerr request matches the media by IDs or title."""
    media = req.get("media") or {}
    if tmdb_id and str(media.get("tmdbId")) == str(tmdb_id):
        return True
    if imdb_id:
        imdb_req = str(media.get("imdbId", "")).strip().lower()
        if imdb_req and imdb_req == str(imdb_id).strip().lower():
            return True
    if title:
        if str(media.get("title", "")).strip().lower() == str(title).strip().lower():
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
    params = {
        "take": 100,
        "skip": 0,
        "filter": "approved",
        "sort": "added",
    }
    r = s.get(f"{base.rstrip('/')}/api/v1/request", params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    results = data.get("results") if isinstance(data, dict) else data
    results = results or []

    for req in results:
        if _matches_media(
            req, tmdb_id=tmdb_id, imdb_id=imdb_id, title=title, year=year
        ):
            return req
    return None


# ====== Main ======
def main():
    p = argparse.ArgumentParser(
        description="Tag Radarr movie on Plex Recently Added (via Tautulli) with Overseerr requester tag."
    )
    p.add_argument("--themoviedb_id")
    p.add_argument("--imdb_id")
    p.add_argument("--title")
    p.add_argument("--year")
    args = p.parse_args()

    RADARR_URL = radarr_base_url()
    RADARR_API_KEY = _env("RADARR_API_KEY", required=True)
    OVERSEERR_URL = overseerr_base_url()
    OVERSEERR_API_KEY = overseerr_api_key()

    r_session = radarr_session(RADARR_API_KEY)
    o_session = overseerr_session(OVERSEERR_API_KEY)

    try:
        movie = find_movie(
            r_session,
            RADARR_URL,
            tmdb_id=args.themoviedb_id,
            imdb_id=args.imdb_id,
            title=args.title,
            year=args.year,
        )
    except Exception as e:
        fail(f"Radarr lookup failed: {e}")

    if not movie:
        fail(
            f"No matching movie in Radarr (tmdb={args.themoviedb_id!r}, imdb={args.imdb_id!r}, "
            f"title={args.title!r}, year={args.year!r})."
        )

    movie_id = movie.get("id")
    if not movie_id:
        fail("Matched Radarr movie missing 'id'.")

    try:
        req = find_overseerr_request(
            o_session,
            OVERSEERR_URL,
            tmdb_id=args.themoviedb_id,
            imdb_id=args.imdb_id,
            title=args.title,
            year=args.year,
        )
    except Exception as e:
        fail(f"Overseerr lookup failed: {e}")

    requester_user = extract_requester(req) if req else None
    tag_label = requester_tag(requester_user)

    try:
        tag_id = ensure_tag(r_session, RADARR_URL, tag_label)
        overseer_id = ensure_tag(r_session, RADARR_URL, "overseer")
        add_tags_to_movie(r_session, RADARR_URL, int(movie_id), [tag_id, overseer_id])
    except Exception as e:
        fail(f"Applying tags failed: {e}")

    requester_display = None
    if requester_user:
        for key in ("displayName", "username", "email"):
            if requester_user.get(key):
                requester_display = requester_user[key]
                break

    print(
        f"[Radarr] Tagged '{movie.get('title')}' ({movie.get('year')}) with ['{tag_label}', 'overseer'] "
        f"(Radarr id={movie_id}, requester={requester_display or 'unknown'})"
    )


if __name__ == "__main__":
    main()
