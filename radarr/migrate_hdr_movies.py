#!/usr/bin/env python3
"""
migrate_hdr_movies.py — Move all movies on the HDR quality profile to /movies-hdr.

Scans every movie in Radarr, checks if its quality profile name contains "HDR",
and moves matching movies that are still in /movies to /movies-hdr via the API.

Usage (run inside the radarr container, or any host that can reach the Radarr API):

    python3 migrate_hdr_movies.py           # dry run — prints what would move
    python3 migrate_hdr_movies.py --apply   # actually move the files

Environment variables:
    RADARR_API_KEY   (required)
    RADARR_URL       (optional, defaults to http://radarr:7878)
"""

import os
import sys

from radarr_utils import _env, fail, radarr_base_url, radarr_session

# ── Config ────────────────────────────────────────────────────────────────────

SDR_ROOT = "/movies"
HDR_ROOT = "/movies-hdr"

# Quality profile names that should live in the HDR folder (case-insensitive substring match).
HDR_PROFILE_KEYWORDS = {"hdr"}

DRY_RUN = "--apply" not in sys.argv


# ── Helpers ───────────────────────────────────────────────────────────────────

def fetch_profiles(s, base: str) -> dict[int, str]:
    """Return {profile_id: profile_name} for all quality profiles."""
    r = s.get(f"{base}/api/v3/qualityprofile", timeout=15)
    r.raise_for_status()
    return {p["id"]: p["name"] for p in r.json()}


def is_hdr_profile(profile_name: str) -> bool:
    name_lower = profile_name.lower()
    return any(kw in name_lower for kw in HDR_PROFILE_KEYWORDS)


def movie_root(movie: dict) -> str:
    return (movie.get("rootFolderPath") or "").rstrip("/")


def move_movies(s, base: str, movie_ids: list[int], target_root: str) -> None:
    payload = {
        "movieIds": movie_ids,
        "rootFolderPath": target_root,
        "moveFiles": True,
    }
    r = s.put(f"{base}/api/v3/movie/editor", json=payload, timeout=120)
    if r.status_code not in (200, 202):
        fail(f"Bulk move failed: HTTP {r.status_code} — {r.text}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    api_key = _env("RADARR_API_KEY", required=True)
    base    = radarr_base_url()
    s       = radarr_session(api_key)

    print(f"[INFO] Fetching quality profiles from {base} …")
    profiles = fetch_profiles(s, base)
    hdr_profile_ids = {pid for pid, name in profiles.items() if is_hdr_profile(name)}

    if not hdr_profile_ids:
        fail("No quality profiles with 'HDR' in the name found. Check Radarr → Settings → Quality Profiles.")

    hdr_profile_names = [profiles[pid] for pid in hdr_profile_ids]
    print(f"[INFO] HDR profile(s) detected: {', '.join(hdr_profile_names)}")

    print(f"[INFO] Fetching movie list …")
    r = s.get(f"{base}/api/v3/movie", timeout=30)
    r.raise_for_status()
    all_movies = r.json()
    print(f"[INFO] {len(all_movies)} movies found in Radarr.")

    to_move: list[dict] = []
    already_hdr: list[dict] = []
    wrong_root: list[dict] = []

    for m in all_movies:
        if m.get("qualityProfileId") not in hdr_profile_ids:
            continue
        root = movie_root(m)
        if root == HDR_ROOT:
            already_hdr.append(m)
        elif root == SDR_ROOT or root == "":
            to_move.append(m)
        else:
            wrong_root.append(m)
            print(f"[WARN] '{m['title']}' is on HDR profile but has unexpected root '{root}' — skipping.")

    print(f"\n── Summary ──────────────────────────────────────────")
    print(f"  Already in {HDR_ROOT}  : {len(already_hdr)}")
    print(f"  To move → {HDR_ROOT}   : {len(to_move)}")
    if wrong_root:
        print(f"  Skipped (unknown root)   : {len(wrong_root)}")
    print(f"─────────────────────────────────────────────────────\n")

    if not to_move:
        print("[INFO] Nothing to do.")
        return

    print("Movies that will be moved:")
    for m in to_move:
        profile_name = profiles.get(m.get("qualityProfileId", -1), "?")
        has_file = "✓ file" if m.get("hasFile") else "  no file yet"
        print(f"  [{has_file}] [{profile_name}] {m['title']} ({m.get('year', '?')})")

    if DRY_RUN:
        print(f"\n[DRY RUN] Re-run with --apply to move {len(to_move)} movie(s).")
        return

    print(f"\n[INFO] Moving {len(to_move)} movie(s) to {HDR_ROOT} …")
    ids = [m["id"] for m in to_move]

    # Split into chunks to avoid timeouts on large batches.
    chunk_size = 20
    for i in range(0, len(ids), chunk_size):
        chunk = ids[i : i + chunk_size]
        titles = [m["title"] for m in to_move[i : i + chunk_size]]
        print(f"  Moving: {', '.join(titles)}")
        move_movies(s, base, chunk, HDR_ROOT)

    print(f"\n[DONE] {len(to_move)} movie(s) moved to {HDR_ROOT}.")


if __name__ == "__main__":
    main()
