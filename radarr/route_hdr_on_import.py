#!/usr/bin/env python3
"""
route_hdr_on_import.py — Radarr Connect script: route HDR-profile movies to /movies-hdr.

Radarr → Settings → Connect → Custom Script
  Events to enable:  On Movie Added ✓
  Path: /config/scripts/route_hdr_on_import.py   (mapped inside the container)

When a movie is added to Radarr with an HDR quality profile, this script
immediately updates its root folder to /movies-hdr — before any download
starts. No post-import reshuffling needed.

The quality profile is matched by name: any profile whose name contains "hdr"
(case-insensitive) is treated as an HDR profile. Change HDR_PROFILE_KEYWORDS
below if your profile uses a different naming convention.

Environment variables injected by Radarr:
    radarr_eventtype     — "MovieAdded", "Test", …
    radarr_movie_id      — numeric Radarr movie ID

The API key is read from:
    RADARR_API_KEY  (injected by the Docker entrypoint from the secret)
"""

import os
import sys

from radarr_utils import _env, fail, radarr_base_url, radarr_session

# ── Config ────────────────────────────────────────────────────────────────────

SDR_ROOT = "/movies"
HDR_ROOT = "/movies-hdr"

# Case-insensitive substrings to match against quality profile names.
HDR_PROFILE_KEYWORDS = {"hdr"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def is_hdr_profile(name: str) -> bool:
    name_lower = name.lower()
    return any(kw in name_lower for kw in HDR_PROFILE_KEYWORDS)


def get_profile_name(s, base: str, profile_id: int) -> str:
    r = s.get(f"{base}/api/v3/qualityprofile/{profile_id}", timeout=10)
    if r.status_code == 200:
        return r.json().get("name", "")
    return ""


def set_root_folder(s, base: str, movie_id: int, root: str) -> None:
    """Update a movie's root folder (no file to move yet — movie was just added)."""
    payload = {
        "movieIds": [movie_id],
        "rootFolderPath": root,
        "moveFiles": False,
    }
    r = s.put(f"{base}/api/v3/movie/editor", json=payload, timeout=30)
    if r.status_code not in (200, 202):
        fail(f"Root folder update failed: HTTP {r.status_code} — {r.text}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    event = os.getenv("radarr_eventtype", "").strip()

    if event == "Test":
        print("[INFO] Test event received — script is working correctly.")
        sys.exit(0)

    if event != "MovieAdded":
        print(f"[INFO] Ignoring event type '{event}'.")
        sys.exit(0)

    movie_id_str = os.getenv("radarr_movie_id", "").strip()
    if not movie_id_str or not movie_id_str.isdigit():
        fail("radarr_movie_id is missing or not numeric.")
    movie_id = int(movie_id_str)

    api_key = _env("RADARR_API_KEY", required=True)
    base    = radarr_base_url()
    s       = radarr_session(api_key)

    r = s.get(f"{base}/api/v3/movie/{movie_id}", timeout=15)
    if r.status_code == 404:
        fail(f"Movie ID {movie_id} not found in Radarr.")
    r.raise_for_status()
    movie = r.json()

    title        = movie.get("title", f"ID:{movie_id}")
    profile_id   = movie.get("qualityProfileId")
    current_root = (movie.get("rootFolderPath") or "").rstrip("/")

    profile_name = get_profile_name(s, base, profile_id) if profile_id else ""

    if not is_hdr_profile(profile_name):
        print(f"[INFO] '{title}' uses profile '{profile_name}' — not HDR, no action.")
        sys.exit(0)

    if current_root == HDR_ROOT:
        print(f"[INFO] '{title}' is already in {HDR_ROOT}.")
        sys.exit(0)

    print(f"[INFO] '{title}' added with profile '{profile_name}' — routing to {HDR_ROOT} …")
    set_root_folder(s, base, movie_id, HDR_ROOT)
    print(f"[DONE] '{title}' root folder set to {HDR_ROOT}.")


if __name__ == "__main__":
    main()
