#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Tautulli Script: On Plex "Watched", tag the movie in Radarr and post a clickable
# Letterboxd log link to Discord.

# - Adds tags: "{username}-watched" and "tbd" (creates tags if missing).
# - Discord webhook message includes:
#     [Open in Letterboxd app] (letterboxd://x-callback-url/log?... )
#     [Or view on the web] (https://letterboxd.com/...)

# Tautulli Script Arguments:
#   --themoviedb_id {themoviedb_id} --imdb_id {imdb_id} --title "{title}" --year {year} --username "{username}"

# Env on Tautulli host/container:
#   RADARR_API_KEY
#   RADARR_URL   (optional; defaults to http://localhost:<RADARR_PORT|7878>)
#   RADARR_PORT  (optional; defaults to 7878)

import argparse
import os
from datetime import datetime
from urllib.parse import urlencode, quote_plus

from tautulli_utils import (
    _clean_username,
    _env,
    fail,
    radarr_base_url,
    radarr_session,
    find_movie,
    ensure_tag,
    add_tags_to_movie,
    discord_post,
)


# ====== CONFIG ======
# List of usernames to post Letterboxd log links for
LETTERBOXD_USERS = os.getenv("LETTERBOXD_USERS", "").split(",")
LETTERBOXD_USERS = [u.strip().lower() for u in LETTERBOXD_USERS if u.strip()]


# ====== Letterboxd ======
def letterboxd_log_link(username: str, title: str, year=None) -> None:
    """Post a Letterboxd log link to Discord (clickable) for configured users."""
    if str(username).strip().lower() not in LETTERBOXD_USERS:
        return

    name = f"{title} ({year})" if year else title

    # Deep link into the app
    app_link = "letterboxd://x-callback-url/log?" + urlencode(
        {
            "name": name,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "tags": "plex",
        }
    )

    # Web fallback
    web_fallback = f"https://letterboxd.com/search/films/{quote_plus(name)}"

    content = (
        f"🎬 **Log to Letterboxd**\n"
        f"**Movie:** {name}\n"
        f"[Open in Letterboxd app]({app_link})\n"
        f"[Or view on the web]({web_fallback})"
    )
    discord_post(content)


# ====== Main ======
def main():
    p = argparse.ArgumentParser(
        description="Tag Radarr movie on Plex Watched (via Tautulli) and post to Discord."
    )
    p.add_argument("--themoviedb_id")
    p.add_argument("--imdb_id")
    p.add_argument("--title")
    p.add_argument("--year")
    p.add_argument("--username")
    args = p.parse_args()

    RADARR_URL = radarr_base_url()
    RADARR_API_KEY = _env("RADARR_API_KEY", required=True)

    s = radarr_session(RADARR_API_KEY)

    try:
        movie = find_movie(
            s,
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
            f"No matching movie in Radarr (tmdb={args.themoviedb_id!r}, imdb={args.imdb_id!r}, title={args.title!r}, year={args.year!r})."
        )

    movie_id = movie.get("id")
    if not movie_id:
        fail("Matched Radarr movie missing 'id'.")

    username = args.username or "unknown"
    cleaned = _clean_username(username)
    # Fallback to "unknown" if username has no valid chars (e.g., Japanese)
    watched_tag_label = f"{cleaned or 'unknown'}-watched"

    try:
        watched_id = ensure_tag(s, RADARR_URL, watched_tag_label)
        tbd_id = ensure_tag(s, RADARR_URL, "tbd")
        add_tags_to_movie(s, RADARR_URL, int(movie_id), [watched_id, tbd_id])
    except Exception as e:
        fail(f"Applying tags failed: {e}")

    print(
        f"[Radarr] Tagged '{movie.get('title')}' ({movie.get('year')}) with ['{watched_tag_label}', 'tbd'] "
        f"(Radarr id={movie_id}, user={username})"
    )

    # Post to Discord Letterboxd link if configured
    letterboxd_log_link(
        args.username or "",
        movie.get("title"),
        movie.get("year"),
    )


if __name__ == "__main__":
    main()
