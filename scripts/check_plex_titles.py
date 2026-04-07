#!/usr/bin/env python3
"""
Compare Plex library items to Kometa-style asset folder names on disk.

Credentials (first match wins for URL / token):

  • Process environment — e.g. Kometa Docker sets KOMETA_PLEXURL and KOMETA_PLEXTOKEN
    (see ortflix/compose/docker-compose-onelayer.yml).
  • This directory's .env — load_dotenv(..., override=False) fills only unset vars.
  • Values may be literals, a file path, or `sudo cat /path/to/secret` on this machine.

If KOMETA_PLEXURL is unset or unreadable but ORTFLIX_SYNC_HOST is set, URL defaults to
http://ORTFLIX_SYNC_HOST:32400 (port: KOMETA_PLEX_PORT).

Usage:
    python3 scripts/check_plex_titles.py
    python3 scripts/check_plex_titles.py Films "4K Movies"
    python3 scripts/check_plex_titles.py Films Series --summary
    python3 scripts/check_plex_titles.py Films --asset-dir /path/to/Movies_Shows
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from argparse import ArgumentParser
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from plexapi.server import PlexServer

SCRIPT_DIR = Path(__file__).resolve().parent
COSTUME_ROOT = SCRIPT_DIR.parent
DOTENV_PATH = SCRIPT_DIR / ".env"
KOMETA_ROOT = COSTUME_ROOT / "kometa"
DEFAULT_ASSET_DIR = KOMETA_ROOT / "config" / "assets" / "Movies_Shows"
EXCEPTION_MAPPINGS_PATH = KOMETA_ROOT / "tools" / "asset-organizer" / "exception_mappings.json"

load_dotenv(DOTENV_PATH, override=False)

DEFAULT_LIBRARIES = ("Films",)

GUID_PREFIXES = (
    ("imdb://", "imdb-"),
    ("tmdb://", "tmdb-"),
    ("tvdb://", "tvdb-"),
)


def _try_resolve_secret(raw: str | None) -> str | None:
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
                ["sudo", "cat", str(path)],
                capture_output=True,
                text=True,
                timeout=60,
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


def load_plex_config() -> tuple[str, str]:
    url = _try_resolve_secret(os.getenv("KOMETA_PLEXURL"))
    if not url:
        host = os.getenv("ORTFLIX_SYNC_HOST", "").strip()
        if host:
            port = os.getenv("KOMETA_PLEX_PORT", "32400").strip() or "32400"
            url = f"http://{host}:{port}"

    token = _try_resolve_secret(os.getenv("KOMETA_PLEXTOKEN"))

    if not url or not token:
        lines = []
        if not url:
            lines.append(
                "Plex URL: set KOMETA_PLEXURL, or ORTFLIX_SYNC_HOST (uses http://HOST:32400)."
            )
        if not token:
            lines.append(
                "Plex token: set KOMETA_PLEXTOKEN (literal, file path, or sudo cat on this machine)."
            )
        print("Error:\n" + "\n".join(f"  {x}" for x in lines))
        raise SystemExit(1)

    return url, token


def _load_exception_mappings(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _normalize_name(name: str, exception_mappings: dict[str, str]) -> str:
    if name in exception_mappings:
        return exception_mappings[name]
    name = name.replace(":", " -")
    if name in exception_mappings:
        return exception_mappings[name]
    return name


def _extract_ids(item: Any) -> set[str]:
    ids: set[str] = set()
    for guid in getattr(item, "guids", None) or []:
        gid = str(getattr(guid, "id", ""))
        for prefix, label in GUID_PREFIXES:
            if gid.startswith(prefix):
                clean = gid[len(prefix) :].split("?")[0]
                ids.add(f"{label}{clean}")
    return ids


def _folder_asset_name(item: Any) -> str:
    try:
        media = getattr(item, "media", None)
        if media:
            parts = media[0].parts if hasattr(media[0], "parts") else []
            if parts:
                return Path(parts[0].file).parent.name
    except (AttributeError, IndexError, TypeError):
        pass
    y = getattr(item, "year", None)
    title = getattr(item, "title", "") or ""
    return f"{title} ({y})" if y else title


def _title_variations_for_orphan(item: Any) -> set[str]:
    t = getattr(item, "title", "") or ""
    out = {t}
    y = getattr(item, "year", None)
    if y is not None:
        out.add(f"{t} ({y})")
    return out


def analyze_section(
    section: Any,
    asset_folders: set[str],
    exception_mappings: dict[str, str],
) -> tuple[list[tuple[str, Any, str]], list[tuple[str, Any, str]], list[Any], set[str]]:
    """Return (matched_rows, missing_rows, items, claimed_folders) for one library section."""
    items = section.all()
    matched: list[tuple[str, Any, str]] = []
    missing: list[tuple[str, Any, str]] = []
    claimed: set[str] = set()

    def sort_key(it: Any) -> str:
        return (getattr(it, "title", "") or "").lower()

    for item in sorted(items, key=sort_key):
        title = getattr(item, "title", "") or ""
        year = getattr(item, "year", None)
        year_disp = year if year is not None else "N/A"
        folder_name = _folder_asset_name(item)
        candidate_ids = _extract_ids(item)

        variations = [
            title,
            f"{title} ({year_disp})",
            _normalize_name(title, exception_mappings),
            _normalize_name(f"{title} ({year_disp})", exception_mappings),
            folder_name,
        ]
        for ext_id in candidate_ids:
            variations.append(f"{title} ({year_disp}) {{{ext_id}}}")
            variations.append(f"{title} {{{ext_id}}}")

        found = next((v for v in variations if v in asset_folders), None)
        if found:
            note = f'matched as "{found}"' if found != title else "matched"
            matched.append((title, year_disp, note))
            claimed.add(found)
        else:
            missing.append((title, year_disp, folder_name))

    return matched, missing, items, claimed


def _print_library_report(
    section_title: str,
    matched: list[tuple[str, Any, str]],
    missing: list[tuple[str, Any, str]],
    *,
    summary_only: bool,
) -> None:
    sep = "-" * 80
    print(sep)
    print(f"Library: {section_title}")
    print(sep)
    print(f"With asset folder match: {len(matched)}")
    if not summary_only:
        for title, year, note in matched:
            print(f"  [OK]   {title} ({year})  {note}")
    print()
    print(f"Missing asset folder: {len(missing)}")
    if not summary_only:
        for title, year, expected in missing:
            print(f"  [MISS] {title} ({year})  expected folder name: {expected}")
    print()


def main() -> None:
    parser = ArgumentParser(
        description="List Plex library items and compare folder names to asset directories."
    )
    parser.add_argument(
        "libraries",
        nargs="*",
        metavar="LIBRARY",
        help="Plex library names (default: Films). Example: Films Series",
    )
    parser.add_argument(
        "--asset-dir",
        default=None,
        help=f"Asset root (default: {DEFAULT_ASSET_DIR})",
    )
    parser.add_argument(
        "--summary",
        "-s",
        action="store_true",
        help="Counts per library and final summary only (no per-item [OK]/[MISS] lines).",
    )
    args = parser.parse_args()

    library_names = list(args.libraries) if args.libraries else list(DEFAULT_LIBRARIES)

    plex_url, plex_token = load_plex_config()
    print(f"Plex: {plex_url}")
    print(f"Libraries: {', '.join(library_names)}")
    print()

    plex = PlexServer(plex_url, plex_token)
    available = {s.title: s for s in plex.library.sections()}
    missing_names = [n for n in library_names if n not in available]
    if missing_names:
        print("Error: unknown library name(s):", ", ".join(missing_names))
        print("Available:", ", ".join(sorted(available.keys())))
        raise SystemExit(1)

    asset_dir = Path(args.asset_dir) if args.asset_dir else DEFAULT_ASSET_DIR
    if asset_dir.is_dir():
        asset_folders = {
            name
            for name in os.listdir(asset_dir)
            if (asset_dir / name).is_dir() and not name.startswith(".")
        }
    else:
        print(f"Warning: asset directory does not exist or is not a directory: {asset_dir}")
        print("Treating as no asset folders.")
        asset_folders = set()

    exception_mappings = _load_exception_mappings(EXCEPTION_MAPPINGS_PATH)
    if not EXCEPTION_MAPPINGS_PATH.is_file() and EXCEPTION_MAPPINGS_PATH.parent.is_dir():
        print(f"Note: optional file not found: {EXCEPTION_MAPPINGS_PATH}")
        print()

    all_items: list[Any] = []
    all_title_hints: set[str] = set()

    grand_matched = 0
    grand_missing = 0

    all_claimed_folders: set[str] = set()

    for name in library_names:
        section = available[name]
        matched, missing, items, claimed = analyze_section(
            section, asset_folders, exception_mappings
        )
        all_items.extend(items)
        for it in items:
            all_title_hints |= _title_variations_for_orphan(it)
        all_claimed_folders |= claimed
        grand_matched += len(matched)
        grand_missing += len(missing)
        _print_library_report(name, matched, missing, summary_only=args.summary)

    orphaned = (asset_folders - all_title_hints) - all_claimed_folders
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"  Libraries checked:     {len(library_names)}")
    print(f"  Total items scanned:   {len(all_items)}")
    print(f"  With asset match:      {grand_matched}")
    print(f"  Missing asset folder:  {grand_missing}")
    print(
        f"  Orphan asset folders:  {len(orphaned)}  "
        "(folder name not equal to item title or 'title (year)' in scanned libraries)"
    )
    if orphaned:
        print()
        print("Orphan folders (by name):")
        for folder in sorted(orphaned):
            print(f"  {folder}")
    print()


if __name__ == "__main__":
    main()
