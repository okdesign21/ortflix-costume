#!/usr/bin/env python3
"""
update_jewish_dates.py
~~~~~~~~~~~~~~~~~~~~~~
Fetches the next occurrence of Purim, Passover, Yom Ha'atzmaut, and
Hanukkah via the free HebCal public API, then rewrites the
start_date / end_date schedule windows in:

    ../kometa/config/israeli_holidays.yml

Requirements
------------
    pip install requests

Usage
-----
    python update_jewish_dates.py              # update in-place
    python update_jewish_dates.py --dry-run    # preview changes only
    python update_jewish_dates.py --year 2027  # base all lookups on 2027
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("'requests' is not installed.  Run: pip install requests")


# ── paths ─────────────────────────────────────────────────────────────────────

THIS_DIR    = Path(__file__).parent.resolve()
CONFIG_FILE = THIS_DIR.parent / "kometa" / "config" / "israeli_holidays.yml"

# ── holiday window offsets (days relative to the anchor / first-day date) ─────
#
#   Negative  = days BEFORE the holiday starts (lead-up window)
#   Positive  = days AFTER  the anchor date     (tail window)
#
WINDOWS: dict[str, tuple[int, int]] = {
    "Purim":         (-10,  +3),   # 10 days before → day after Shushan Purim
    "Passover":      ( -7,  +8),   # week before → full 8-day chag
    "Yom Haatzmaut": ( -5,  +3),   # includes Yom HaZikaron eve
    "Hanukkah":      ( -3, +11),   # 3 days before first candle → end of 8th night
}

# Internal holiday key → collection name exactly as written in the YAML
YAML_COLLECTION: dict[str, str] = {
    "Purim":         "Purim Movies",
    "Passover":      "Passover Movies",
    "Yom Haatzmaut": "Yom Ha'atzmaut Movies",
    "Hanukkah":      "Hanukkah Movies",
}

HEBCAL_API = "https://www.hebcal.com/hebcal"


# ── HebCal helpers ────────────────────────────────────────────────────────────

def _fetch_year(year: int) -> list[dict]:
    """Return all HebCal holiday items for a Gregorian year."""
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    resp = requests.get(
        HEBCAL_API,
        params={
            "v":   1,
            "cfg": "json",
            "year": year,
            "maj": "on",   # major holidays (Purim, Pesach, Hanukkah, …)
            "mod": "on",   # modern Israeli holidays (Yom HaAtzma'ut, Yom HaShoah, …)
            "min": "off",  # skip minor fasts / Rosh Chodesh
            "nx":  "off",
            "mf":  "off",
            "ss":  "off",
            "i":   "off",  # diaspora schedule → Pesach I = first seder night
            "geo": "none",
        },
        timeout=15,
        verify=False,   # matches network-wide verify_ssl: false (self-signed cert chain)
    )
    resp.raise_for_status()
    return resp.json().get("items", [])


def _classify(title: str) -> str | None:
    """Map a HebCal item title to our internal holiday key, or None."""
    if title == "Purim":
        return "Purim"
    if title in ("Pesach I", "Pesach"):
        return "Passover"
    if "Yom" in title and "Atzma" in title:   # avoids ASCII vs Unicode apostrophe mismatch
        return "Yom Haatzmaut"
    if "Chanukah" in title and "1 Candle" in title:
        return "Hanukkah"
    return None


def find_next_holidays(from_date: datetime.date) -> dict[str, datetime.date]:
    """
    Return the next anchor date (on or after from_date) for every holiday in
    WINDOWS.  Queries the current year first; falls back to the next year for
    any holidays that have already passed.
    """
    found: dict[str, datetime.date] = {}
    for year in (from_date.year, from_date.year + 1):
        if len(found) == len(WINDOWS):
            break
        for item in _fetch_year(year):
            title  = item.get("title", "")
            key    = _classify(title)
            if key is None or key in found:
                continue
            anchor = datetime.date.fromisoformat(item["date"][:10])
            if anchor >= from_date:
                found[key] = anchor
    return found


# ── YAML patching ─────────────────────────────────────────────────────────────

def _mmdd(d: datetime.date) -> str:
    return d.strftime("%m/%d")


def _patch_collection(text: str, collection_name: str, start: str, end: str) -> tuple[str, bool]:
    """
    Replace the start_date and end_date inside a specific collection's
    template block.  Returns (new_text, changed).

    Pattern explanation:
      - Matches the indented collection header line
      - Then lazily captures everything up to the start_date value
      - Replaces that date value, then carries on to end_date and replaces it
    The DOTALL flag lets .* cross newlines so we can span the template block.
    """
    pattern = (
        r"([ \t]+"
        + re.escape(collection_name)
        + r":.*?start_date:\s*)(\d{2}/\d{2})"
        r"(.*?end_date:\s*)(\d{2}/\d{2})"
    )
    new_text, n = re.subn(
        pattern,
        lambda m: m.group(1) + start + m.group(3) + end,
        text,
        count=1,
        flags=re.DOTALL,
    )
    return new_text, n > 0


def apply_ranges(
    path: Path,
    ranges: dict[str, tuple[str, str]],
    dry_run: bool,
) -> None:
    original = path.read_text(encoding="utf-8")
    text     = original

    print(f"\nTarget file: {path}\n")
    any_changed = False
    for key, (start_str, end_str) in ranges.items():
        coll = YAML_COLLECTION[key]
        text, ok = _patch_collection(text, coll, start_str, end_str)
        if ok:
            any_changed = True
            print(f"  {coll:<32s}  {start_str} .. {end_str}")
        else:
            print(f"  WARNING: could not locate '{coll}' — skipped")

    if not any_changed:
        print("  No changes to apply.")
        return

    if dry_run:
        print("\n[dry-run] Changes were NOT written.  Diff preview:\n")
        orig_lines = original.splitlines()
        new_lines  = text.splitlines()
        for i, (a, b) in enumerate(zip(orig_lines, new_lines), start=1):
            if a != b:
                print(f"  line {i:4d}  -  {a.strip()}")
                print(f"          +  {b.strip()}")
    else:
        path.write_text(text, encoding="utf-8")
        print(f"\n  Written: {path}")


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch the next occurrence of each Jewish holiday via the HebCal "
            "API and update the schedule windows in israeli_holidays.yml."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing the file",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        metavar="YYYY",
        help="Treat Jan 1 of YYYY as today (useful for forward planning)",
    )
    args = parser.parse_args()

    today = (
        datetime.date(args.year, 1, 1)
        if args.year
        else datetime.date.today()
    )

    print(f"Fetching Jewish holidays from {today} onwards …")

    try:
        holidays = find_next_holidays(today)
    except requests.RequestException as exc:
        sys.exit(f"HebCal API error: {exc}")

    if not holidays:
        sys.exit("HebCal returned no matching holidays — check network access.")

    print(f"\n  {'Holiday':<22s}  {'Anchor':<12s}  Window (MM/DD)")
    print(f"  {'-'*22}  {'-'*12}  {'-'*18}")

    ranges: dict[str, tuple[str, str]] = {}
    for key in WINDOWS:
        if key not in holidays:
            print(f"  {key:<22s}  (not found — skipped)")
            continue
        anchor       = holidays[key]
        pre, post    = WINDOWS[key]
        start        = anchor + datetime.timedelta(days=pre)
        end          = anchor + datetime.timedelta(days=post)
        ranges[key]  = (_mmdd(start), _mmdd(end))
        print(f"  {key:<22s}  {str(anchor):<12s}  {_mmdd(start)} .. {_mmdd(end)}")

    apply_ranges(CONFIG_FILE, ranges, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
