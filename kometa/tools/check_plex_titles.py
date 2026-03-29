#!/usr/bin/env python3
"""
Extract all movie titles from Plex to compare with asset folder names.

Usage:
    python3 check_plex_titles.py                          # Uses default library 'Films'
    python3 check_plex_titles.py MyLibrary                # Override library name
    python3 check_plex_titles.py --asset-dir ../assets    # Override asset directory (default: config/assets/Movies_Shows)
"""

import os
from pathlib import Path
from argparse import ArgumentParser
from plexapi.server import PlexServer
from dotenv import load_dotenv
import json

# Get script directory for relative paths
SCRIPT_DIR = Path(__file__).resolve()

# Load environment variables from .env in same directory as script
ENV_FILE = SCRIPT_DIR.parent / ".env"
load_dotenv(ENV_FILE)

PLEX_URL = os.getenv("KOMETA_PLEXURL")
PLEX_TOKEN = os.getenv("KOMETA_PLEXTOKEN")


def main():
    parser = ArgumentParser(description="Check Plex movies against asset folders")
    parser.add_argument(
        "library",
        nargs="?",
        default="Films",
        help="Plex library name (default: test_movie_lib)",
    )
    parser.add_argument(
        "--asset-dir",
        default=None,
        help="Override asset directory (default: config/assets)",
    )
    args = parser.parse_args()

    library_name = args.library

    print(f"Connecting to Plex at {PLEX_URL}...")
    plex = PlexServer(PLEX_URL, PLEX_TOKEN)

    # Get the movie library
    try:
        library = plex.library.section(library_name)
    except Exception:
        print(f"Error: Could not find library '{library_name}'")
        print(f"Available libraries: {[lib.title for lib in plex.library.sections()]}")
        return

    print(f"\nFetching movies from '{library_name}'...")
    movies = library.all()

    print(f"\n{'=' * 80}")
    print(f"Found {len(movies)} movies in Plex")
    print(f"{'=' * 80}\n")

    # Asset directory - default assets/Movies_Shows next to script
    asset_dir = (
        Path(args.asset_dir)
        if args.asset_dir
        else SCRIPT_DIR.parent / "assets/Movies_Shows"
    )

    # Get existing asset folders
    if os.path.exists(asset_dir):
        asset_folders = {
            f
            for f in os.listdir(asset_dir)
            if os.path.isdir(os.path.join(asset_dir, f)) and not f.startswith(".")
        }
    else:
        asset_folders = set()

    def extract_ids(movie):
        """Collect external ids for flexible folder matching."""
        ids = set()
        for guid in getattr(movie, "guids", []) or []:
            gid = str(getattr(guid, "id", ""))
            for prefix, label in [
                ("imdb://", "imdb-"),
                ("tmdb://", "tmdb-"),
                ("tvdb://", "tvdb-"),
            ]:
                if gid.startswith(prefix):
                    clean = gid[len(prefix) :].split("?")[0]
                    ids.add(f"{label}{clean}")
        return ids

    def get_folder_asset_name(movie):
        """Return the Plex movie's parent folder name used by Kometa asset matching.
        Falls back to title/year if media path is unavailable.
        """
        try:
            media = getattr(movie, "media", None)
            if media:
                parts = media[0].parts if hasattr(media[0], "parts") else []
                if parts:
                    file_path = Path(parts[0].file)
                    return file_path.parent.name
        except (AttributeError, IndexError, TypeError):
            pass
        # Fallback
        y = movie.year if hasattr(movie, "year") else None
        return f"{movie.title} ({y})" if y else movie.title

    # Load exception mappings from external JSON file
    exception_file = SCRIPT_DIR.parent / "asset-organizer" / "exception_mappings.json"
    if exception_file.exists():
        with open(exception_file, "r") as f:
            exception_mappings = json.load(f)
    else:
        print(f"⚠️  Exception mappings file not found: {exception_file}")
        exception_mappings = {}

    def normalize_name(name: str) -> str:
        """Normalize folder names to match Kometa's expected naming conventions."""
        # Check exact match first (for cases where poster downloads already have dashes)
        if name in exception_mappings:
            return exception_mappings[name]

        # Replace colons with dashes (standard Plex to Kometa conversion)
        name = name.replace(":", " -")

        # Check mappings again after normalization
        if name in exception_mappings:
            return exception_mappings[name]

        # Return normalized name
        return name

    # Compare
    matched = []
    missing_assets = []

    for movie in sorted(movies, key=lambda m: m.title):
        title = movie.title
        year = movie.year if hasattr(movie, "year") else "N/A"
        folder_asset_name = get_folder_asset_name(movie)

        candidate_ids = extract_ids(movie)

        variations = [
            title,
            f"{title} ({year})",
            normalize_name(title),
            normalize_name(f"{title} ({year})"),
            folder_asset_name,
        ]

        # Add id-based variations to mirror Kometa asset naming patterns
        for ext_id in candidate_ids:
            variations.append(f"{title} ({year}) {{{ext_id}}}")
            variations.append(f"{title} {{{ext_id}}}")

        found = None
        for var in variations:
            if var in asset_folders:
                found = var
                break

        if found:
            matched.append(
                (title, year, f'✅ (as "{found}")' if found != title else "✅")
            )
        else:
            missing_assets.append((title, year, folder_asset_name))

    # Print results
    print("\n📋 MOVIES WITH ASSETS:")
    print("-" * 80)
    for title, year, status in matched:
        print(f"{status} {title} ({year})")

    print(f"\n\n⚠️  MOVIES MISSING ASSETS ({len(missing_assets)}):")
    print("-" * 80)
    for title, year, expected in missing_assets:
        print(f"❌ {title} ({year}) → expected asset folder: {expected}")

    # Check for orphaned asset folders
    plex_titles = {m.title for m in movies}
    plex_titles_with_year = {
        f"{m.title} ({m.year})" for m in movies if hasattr(m, "year")
    }
    all_plex_variations = plex_titles | plex_titles_with_year

    orphaned = asset_folders - all_plex_variations

    if orphaned:
        print(f"\n\n🗂️  ASSET FOLDERS WITHOUT MATCHING PLEX MOVIES ({len(orphaned)}):")
        print("-" * 80)
        for folder in sorted(orphaned):
            print(f"⚠️  {folder}")

    # Summary
    print(f"\n\n{'=' * 80}")
    print("SUMMARY:")
    print(f"  Total Plex Movies: {len(movies)}")
    print(f"  With Assets: {len(matched)}")
    print(f"  Missing Assets: {len(missing_assets)}")
    print(f"  Orphaned Asset Folders: {len(orphaned)}")
    print(f"{'=' * 80}\n")


if __name__ == "__main__":
    main()
