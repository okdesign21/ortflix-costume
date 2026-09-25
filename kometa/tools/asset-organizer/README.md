# Kometa Assets Organizer

Automated asset organization for Kometa. Downloads and organizes posters, overlays, and backgrounds for Plex media collections.

## Features

- **Automatic Poster Organization**: Organize downloaded posters into proper directory structure
- **Overlay Organization**: Mirror custom overlay images into `config/overlays/`, preserving subdirectory structure
- **Plex-Authoritative Matching**: Match downloaded asset names against your actual Plex library (titles, collections, people, genres, studios) instead of guessing via regex — see [Plex-Based Matching](#plex-based-matching) below
- **Exception Handling**: Custom mappings for genuine one-off title overrides (Kometa `title_override`/`name_mapping` cases)
- **Exception Mapping Bootstrap**: Optional auto-create for missing `exception_mappings.json`
- **Incremental Mode**: Skip unchanged assets using SHA-256 source hash sidecars; re-process only new or updated files
- **Extensible Architecture**: Support for multiple asset types (posters, overlays, backgrounds)
- **Dry-run Mode**: Preview changes before applying them
- **Environment-driven Configuration**: Flexible setup via environment variables or .env files
- **Robust Name Normalization**: Handles common punctuation/unicode mismatches (`:`, `*`, `·`, double spaces) as a fallback when Plex/TMDb don't have a match
- **Docker Ready**: Includes Dockerfile for containerized deployment

## Requirements

- Python 3.11+
- Optional: Pillow (PIL) for PNG conversion; without it files are copied as-is
- Optional: `plexapi` (`pip install .[plex]`) for Plex-based authoritative matching
- Required packages (see handler requirements)

## Plex-Based Matching

Instead of reconstructing the correct asset folder name purely from string
transforms (`normalize_name`'s old colon/asterisk/space rules) plus an
ever-growing `exception_mappings.json`, the organizer can query your Plex
server directly and build an index of the *actual* titles, collections,
people, genres, and studios it already knows about (`plex_index.py`). Source
names are then matched against this index (`matcher.py`) instead of guessed:

1. **`exception_mappings.json`** — exact override, always wins. Reserve this
   for genuine one-offs (Kometa `title_override`/`name_mapping` renames).
2. **Plex index — exact match** — used verbatim.
3. **Plex index — fuzzy match** (`difflib`, cutoff configurable) — used, but
   flagged in the end-of-run **match review** so you can verify it.
4. **Legacy regex normalization** — colon→dash, asterisk→dash, etc. — applied
   when Plex has no match at all.
5. **TMDb search** — last resort, only for `Title (YYYY)`-shaped names not
   yet in your Plex library (e.g. upcoming additions). Results are cached and
   written back to `exception_mappings.json`.

Categories map to Plex index tables as follows: `Movies_Shows` → titles and
collections (checked together, since a top-level poster file could be
either); `People` → cast/crew names; `Genres` → genre tags; `Companies` →
studio/network values.

### Match review

Any fuzzy or unmatched result is written to `match_review.json` (path
configurable via `--match-review-output`) at the end of a run, and logged as
warnings. Use it to spot-check fuzzy matches and to decide which unmatched
items genuinely need a new `exception_mappings.json` entry versus items not
yet added to Plex.

### Plex environment variables

| Variable                  | Required | Default                | Description                                                                                   |
| -------------------------- | -------- | ----------------------- | ----------------------------------------------------------------------------------------------- |
| `KOMETA_PLEXURL`            | ❌       | derived from `ORTFLIX_SYNC_HOST` | Plex server base URL. Literal, file path, or `sudo cat /path/to/secret`.                 |
| `KOMETA_PLEXTOKEN`          | ❌ (recommended) | *(none)*        | Plex auth token. Literal, file path, or `sudo cat /path/to/secret`.                            |
| `ASSET_PLEX_MATCHING`       | ❌       | `true`                  | Master switch for Plex-based matching (`--no-plex` disables it for one run).                    |
| `ASSET_PLEX_LIBRARIES`      | ❌       | `Films,TV Programmes`   | Comma-separated Plex library names to index.                                                    |
| `ASSET_PLEX_INDEX_CACHE`    | ❌       | `plex_index_cache.json` | Path to the cached Plex title index snapshot (not committed to git).                            |
| `ASSET_PLEX_INDEX_MAX_AGE_HOURS` | ❌  | `24`                    | Rebuild the index from Plex once the cache is older than this.                                  |
| `ASSET_PLEX_FUZZY_CUTOFF`   | ❌       | `0.86`                  | Minimum `difflib` similarity ratio (0-1) for a fuzzy match to be accepted.                       |
| `ASSET_MATCH_REVIEW_OUTPUT` | ❌       | `match_review.json`     | Path to write the end-of-run fuzzy/unmatched match review (not committed to git).                |

When Plex credentials are unset, or the server is unreachable and no usable
cache exists, the organizer degrades gracefully to legacy normalization —
Plex matching never blocks or crashes a run.

## Environment Variables

| Variable                         | Required | Default                   | Description                                                                                                                                                                                                                                                                      |
| -------------------------------- | -------- | ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `POSTERS_SOURCE_DIR`             | ❌       | `Posters`                 | Source directory for downloaded poster assets                                                                                                                                                                                                                                    |
| `OVERLAYS_SOURCE_DIR`            | ❌       | `Overlays`                | Source directory for custom overlay images                                                                                                                                                                                                                                       |
| `ASSET_TARGET_DIR`               | ❌       | `../../config/assets`     | Target directory for organized poster assets (resolves to `kometa/config/assets`)                                                                                                                                                                                               |
| `OVERLAY_TARGET_DIR`             | ❌       | `../../config/overlays`   | Target directory for organized overlays (resolves to `kometa/config/overlays`)                                                                                                                                                                                                  |
| `ASSET_FORCE_PNG`                | ❌       | `True`                    | Convert all images to PNG format                                                                                                                                                                                                                                                 |
| `ASSET_EXCEPTION_MAPPINGS`       | ❌       | `exception_mappings.json` | Path to exception mappings configuration file                                                                                                                                                                                                                                    |
| `ASSET_INCREMENTAL`              | ❌       | `false`                   | Skip assets whose source hash matches the last run; only process new or changed files                                                                                                                                                                                            |
| `KOMETA_STRIP_COLLECTION_SUFFIX` | ❌       | `true`                    | Strip trailing ` Collection` from `Movies_Shows` folder names so output matches Kometa's movie [franchise default](https://kometa.wiki/en/latest/defaults/movie/franchise/) (`remove_suffix: Collection`). Set to `false` if your Plex collections keep the full TMDb-style title. |

See [Plex environment variables](#plex-environment-variables) above for Plex-based matching configuration.

Notes:

- Relative `--source`, `--target`, `--overlays-source`, `--overlays-target`, and `--exception-mappings` paths are resolved from the script directory first, then project root.
- `ASSET_FORCE_PNG` accepts common truthy values like `1`, `true`, `yes`, `on`.

## Setup

### Local Development


1. Navigate to directory:

   ```bash
   cd kometa/asset_helpers/Organize_Downloads
   ```

1. (Recommended) Create a virtual environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

1. Install dependencies:

   ```bash
   pip install .[test]
   ```

1. Run tests with pytest:

   ```bash
   pytest
   ```

1. (Optional) Install development dependencies:

   ```bash
   pip install .[dev]
   ```

### Best Practices

- Keep all tests in the `tests/` directory
- Use `pytest` for running and writing tests
- Add new tests for any new features or bug fixes
- Use a virtual environment for development

### Running the Organizer

1. Set environment variables (optional):

   ```bash
   export POSTERS_SOURCE_DIR="./Posters"
   export ASSET_TARGET_DIR="../../config/assets"
   export ASSET_FORCE_PNG="True"
   ```

1. Run the organizer:

   ```bash
   python organize_assets.py
   ```

1. Dry-run mode (preview changes):

   ```bash
   python organize_assets.py --dry-run
   ```

1. Initialize exception mappings if missing:

   ```bash
   python organize_assets.py --init-exception-mappings
   ```

### CLI Options

```bash
python organize_assets.py \
  --source Posters \
  --target ../../config/assets \
  --exception-mappings exception_mappings.json \
  --force-png \
  --init-exception-mappings
```

- Use `--no-force-png` to keep original file formats.

### Docker

Build and run using Docker:

```bash
docker build -t kometa-assets-organizer .
docker run -v /path/to/posters:/app/Posters \
           -v /path/to/assets:/app/assets \
           -e POSTERS_SOURCE_DIR="/app/Posters" \
           -e ASSET_TARGET_DIR="/app/assets" \
           kometa-assets-organizer
```

### With Kometa

Use this tool as part of your Kometa automation pipeline:

1. **Download assets** (via PosterDB downloader or manual fetch)
1. **Run organizer** to structure them:

   ```bash
   docker run --rm \
     -v $PWD/Posters:/workspace/Posters \
     -v $PWD/assets:/workspace/assets \
     ghcr.io/okdesign21/ortflix/kometa-assets-organizer:latest
   ```

1. **Run Kometa** with `item_assets: true` in collection configs

## Configuration

### Franchise / TMDb collection folders

Downloaded sets are often named like `Cars Collection set by …`. Kometa’s default **Franchise** builder uses `remove_suffix: "Collection"`, so the Plex collection (and Kometa asset folder) is usually **`Cars`**, not `Cars Collection`. The organizer applies the same rule after `normalize_name`, so assets land in `config/assets/Movies_Shows/Cars/poster.png`.

- Re-run the organizer after upgrading; remove stale `… Collection` folders under `Movies_Shows` if you still see duplicate poster slots.
- CLI: `--strip-collection-suffix` / `--no-strip-collection-suffix` overrides the env default.

For collections renamed by Kometa `title_override` / `name_mapping` (e.g. some *Star Wars* sets), add a row in `exception_mappings.json` so the organized folder matches Plex — that stays the right tool for one-off Kometa renames.

### Exception Mappings

With Plex-based matching enabled, `exception_mappings.json` is only needed for
genuine one-offs the Plex/TMDb lookups can't resolve on their own — e.g.
Kometa `title_override`/`name_mapping` renames, or titles Plex knows under a
completely different name than the download set (`"101 Dalmatians (1961)" ->
"One Hundred and One Dalmatians (1961)"`). Simple typos/punctuation
differences (`"A Bugs Life" -> "A Bug's Life"`) are now handled automatically
by the fuzzy Plex match — no entry required.

```json
{
  "The Movie Title": "Movie Title",
  "Special Collection Name": "collection_name"
}
```

Check `match_review.json` after a run before adding a new entry — the item
may already resolve correctly (exact or fuzzy) via Plex.

### Asset Organization Structure

Assets are organized by type and title:

```text
kometa/config/assets/
├── Movie Title (2024)/
│   ├── poster.png
│   ├── background.jpg
│   └── overlay.png
├── TV Show Title/
│   ├── poster.png
│   └── season_01_poster.png
└── Collection Name/
   └── poster.png
```

## Usage Examples

### Organize posters from custom directory

```bash
export POSTERS_SOURCE_DIR="/mnt/downloads/new_posters"
python organize_assets.py
```

### Preview changes without applying

```bash
python organize_assets.py --dry-run
```

### Keep original format (don't force PNG)

```bash
python organize_assets.py --no-force-png
```

### Specify custom exception mappings

```bash
export ASSET_EXCEPTION_MAPPINGS="/path/to/custom_mappings.json"
python organize_assets.py
```

## Handlers

### Poster Handler (`poster_handler.py`)

Organizes poster images for Plex items. Handles:

- Title normalization
- Format conversion to PNG
- Directory structure creation
- Exception mapping for non-standard titles

### Base Organizer (`handlers.py`)

Shared utilities used by all handlers:

- `_ensure_target_dir` to create targets (respects dry-run)
- `_iter_image_files` to walk image files safely
- `normalize_name` with exception mappings
- Unicode-aware normalization (`·`, smart quotes/dashes, spacing cleanup)
- `clear_existing` / `process_file` / `save_as_png` for copy-or-convert workflows
- `update_category_tracking` / `get_category_summary` / `log_category_summary` for per-category reporting

### Testing Notes

- `pytest.ini` includes `pythonpath = .` so local module imports (like `handlers`) work reliably.
- Use `make test` for the standard local test run.

### Overlay Handler (`overlay_handler.py`)

Organizes custom overlay images into `config/overlays/`, preserving the
subdirectory structure from the source. Files stems are normalized via
`normalize_name`. Supports the same `--incremental`, `--dry-run`, and
`--force-png` flags as the poster handler.

Source layout example:

```text
Overlays/
├── SomeOverlay.png          →  config/overlays/SomeOverlay.png
├── Awards/
│   └── Oscars.png           →  config/overlays/Awards/Oscars.png
└── Ratings/
    └── IMDb Top 250.png     →  config/overlays/Ratings/IMDb Top 250.png
```

Reference overlays in Kometa YAML by their relative path under `config/overlays/`.

### Current Status

- Posters: supported
- Overlays: supported
- Backgrounds / Thumbnails: can be added by subclassing `Organizer`

**Future handlers** can be added following the same pattern:

- Background Handler
- Thumbnail Handler

## Troubleshooting

### Assets not organizing

- Verify `ASSET_SOURCE_DIR` contains files
- Check `ASSET_TARGET_DIR` is writable
- Review exception mappings for title mismatches
- Run with `--dry-run` to see what would happen

### Permission denied errors

- Ensure container has write permissions to mount paths
- Check file ownership: `ls -la /path/to/assets`
- Use `chown` if needed

### Files not matching titles

- Review the titles in your Plex library
- Add missing mappings to `exception_mappings.json`
- Run with `--dry-run` to preview expected organization

### PNG conversion failing

- Set `ASSET_FORCE_PNG="False"` to skip conversion
- Check source files are valid images
- Verify Python Pillow (PIL) is installed

## Architecture

- **Modular Design**: Separate handlers for different asset types (posters, overlays, backgrounds)
- **Plex-Authoritative Matching**: `plex_index.py` builds a cached snapshot of real Plex titles/collections/people/genres/studios; `matcher.py` scores source names against it (exact / fuzzy / unmatched) instead of guessing via regex
- **Extensible**: New handlers can be added by subclassing the `Organizer` base class
- **Error Handling**: Comprehensive logging, a fuzzy/unmatched match review, and exception mapping for genuine one-off titles
- **Dry-run Support**: Test changes before applying them with `--dry-run` flag
- **Type Safety**: Uses Python type hints throughout for better IDE support
- **Testing**: Full pytest test suite with coverage reporting

## License

Part of the Ortflix project
