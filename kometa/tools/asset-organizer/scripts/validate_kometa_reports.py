#!/usr/bin/env python3
"""Cross-check Kometa report collection titles vs organizer naming helpers.

Reads YAML reports (top-level keys = Plex collection titles) and flags titles
where normalize_name() would produce a different folder name than Kometa expects.

Optionally parses logs/posters.txt (tree-style listing) to compare inventory
stems to report keys — useful when media files are not on disk.

Usage (from Organize_Downloads, venv active):
  pip install pyyaml
  python scripts/validate_kometa_reports.py \\
    --reports ../../../logs/Films_report.yml ../../../logs/Musicals_report.yml \\
            "../../../logs/TV Programmes_report.yml" \\
    --posters-inventory ../../../logs/posters.txt
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Allow importing handlers when run as script
_ORG = Path(__file__).resolve().parent.parent
if str(_ORG) not in sys.path:
    sys.path.insert(0, str(_ORG))

from poster_handler import PosterOrganizer  # noqa: E402


def load_report_keys(path: Path) -> list[str]:
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return []
    return list(data.keys())


def make_poster_organizer_stub(tmp: Path) -> PosterOrganizer:
    """Use project exception_mappings.json when present so validation matches real runs."""
    exc = _ORG / "exception_mappings.json"
    if not exc.exists():
        exc = tmp / "exceptions.json"
        exc.write_text("{}", encoding="utf-8")
    src, tgt = tmp / "src", tmp / "tgt"
    src.mkdir()
    tgt.mkdir()
    return PosterOrganizer(src, tgt, exc, force_png=True, dry_run=True)


TREE_LINE = re.compile(r"^[│\s]*[├└][─\s]*\s*(.+?)\s*$")


def parse_posters_inventory(path: Path) -> dict[str, set[str]]:
    """Parse a `tree`-style posters.txt into category -> set of raw stems/names."""
    sections: dict[str, set[str]] = {
        "Companies": set(),
        "Genres": set(),
        "Movies_Shows": set(),
    }
    current: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if re.search(r"[├└].*\bCompanies\s*$", line):
            current = "Companies"
            continue
        if re.search(r"[├└].*\bGenres\s*$", line):
            current = "Genres"
            continue
        if re.search(r"[├└].*\bMovies_Shows\s*$", line):
            current = "Movies_Shows"
            continue
        if current is None or not stripped:
            continue
        m = TREE_LINE.match(line)
        if not m:
            continue
        item = m.group(1).strip()
        if not item or item in ("Companies", "Genres", "Movies_Shows"):
            continue
        lower = item.lower()
        if lower.endswith((".jpg", ".jpeg", ".png", ".webp")):
            stem = Path(item).stem
            sections[current].add(stem)
        elif current == "Movies_Shows":
            # Subfolder (e.g. DIIIVOY bundle), not a loose file at category root
            sections[current].add(item)
    return sections


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reports",
        nargs="+",
        type=Path,
        required=True,
        help="Kometa *_report.yml files",
    )
    parser.add_argument(
        "--posters-inventory",
        type=Path,
        default=None,
        help="Optional logs/posters.txt tree listing",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable summary as JSON",
    )
    parser.add_argument(
        "--inventory-overlap",
        action="store_true",
        help="List poster inventory entries whose derived folder name is absent from "
        "report keys (noisy: reports are not a full catalog of all collections)",
    )
    args = parser.parse_args()

    try:
        import yaml  # noqa: F401
    except ImportError:
        print("Install PyYAML: pip install pyyaml", file=sys.stderr)
        return 1

    all_keys: list[str] = []
    per_file: dict[str, list[str]] = {}
    for rp in args.reports:
        keys = load_report_keys(rp)
        per_file[str(rp)] = keys
        all_keys.extend(keys)

    # Dedupe preserving order
    seen: set[str] = set()
    unique_keys: list[str] = []
    for k in all_keys:
        if k not in seen:
            seen.add(k)
            unique_keys.append(k)

    import tempfile

    inventory_derived: dict[str, dict[str, object]] = {}

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        poster = make_poster_organizer_stub(tmp)

        normalize_mismatches: list[dict[str, str]] = []
        for k in unique_keys:
            n = poster.normalize_name(k)
            if n != k:
                normalize_mismatches.append(
                    {"report_title": k, "normalize_name_output": n}
                )

        # Inventory vs reports (best-effort)
        if args.posters_inventory and args.posters_inventory.exists():
            inv = parse_posters_inventory(args.posters_inventory)
            report_set = set(unique_keys)
            for cat, raw_names in inv.items():
                missing_in_reports: list[str] = []
                for raw in sorted(raw_names):
                    if cat in ("Companies", "Genres"):
                        d = poster.normalize_name(raw)
                        if d not in report_set and raw not in report_set:
                            missing_in_reports.append(raw)
                    else:
                        # Movies_Shows: DIIIVOY bundle dirs vs top-level poster stems
                        if " set by " in raw.lower() or re.search(
                            r"-\s*\d{4}-\d{2}-\d{2}\s*$", raw
                        ):
                            coll = poster.extract_collection_name(raw)
                            coll_n = poster.normalize_name(coll)
                            if coll_n not in report_set:
                                missing_in_reports.append(f"{raw} -> {coll_n}")
                        else:
                            d = poster.normalize_name(raw)
                            if d not in report_set and raw not in report_set:
                                missing_in_reports.append(raw)
                inventory_derived[cat] = {
                    "raw_entries_sampled": len(raw_names),
                    "not_in_any_report_key": missing_in_reports[:200],
                    "not_in_any_report_key_count": len(missing_in_reports),
                }

    summary = {
        "report_files": [str(p) for p in args.reports],
        "unique_collection_titles": len(unique_keys),
        "normalize_name_differs_from_report_title": len(normalize_mismatches),
        "normalize_mismatches": normalize_mismatches,
        "per_file_key_counts": {k: len(v) for k, v in per_file.items()},
        "posters_inventory": inventory_derived if inventory_derived else None,
    }

    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    print("Kometa report vs organizer (normalize_name)")
    print(f"  Unique collection titles (all reports): {len(unique_keys)}")
    print(
        f"  Titles where normalize_name(title) != title: {len(normalize_mismatches)}"
    )
    if normalize_mismatches:
        print("\n  These need exception_mappings (or folder names must match Kometa, not normalize output):")
        for row in normalize_mismatches[:50]:
            print(f"    {row['report_title']!r}")
            print(f"      -> normalize_name: {row['normalize_name_output']!r}")
        if len(normalize_mismatches) > 50:
            print(f"    ... and {len(normalize_mismatches) - 50} more")
    else:
        print("  (none — folder names from stems equal to titles would align)")

    if inventory_derived:
        print("\nposters.txt inventory (parsed counts only)")
        for cat, info in inventory_derived.items():
            print(f"  {cat}: {info['raw_entries_sampled']} raw entries")
        if args.inventory_overlap:
            print("\n  --inventory-overlap: entries with derived name not in merged report keys")
            for cat, info in inventory_derived.items():
                nmiss = info["not_in_any_report_key_count"]
                print(f"  {cat}: {nmiss}")
                for line in info["not_in_any_report_key"][:20]:
                    print(f"      - {line}")
                if nmiss > 20:
                    print(f"      ... ({nmiss - 20} more)")
        else:
            print(
                "\n  (Omitting overlap listing: merged reports only include collections "
                "from those library runs, not every studio/genre/movie. "
                "Use --inventory-overlap to list missing-key matches.)"
            )

    print(
        "\nNote: Report keys must match Plex collection titles. "
        "If normalize_name changes punctuation, use exception_mappings.json "
        "so the organizer writes folders that Kometa looks up."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
