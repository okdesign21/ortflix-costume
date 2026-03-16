# Kometa Assets Organizer

Automated asset organization for Kometa. Downloads and organizes posters, overlays, and backgrounds for Plex media collections.

## Features

- **Automatic Poster Organization**: Organize downloaded posters into proper directory structure
- **Exception Handling**: Custom mappings for non-standard title formats
- **Exception Mapping Bootstrap**: Optional auto-create for missing `exception_mappings.json`
- **Extensible Architecture**: Support for multiple asset types (posters, overlays, backgrounds)
- **Dry-run Mode**: Preview changes before applying them
- **Environment-driven Configuration**: Flexible setup via environment variables or .env files
- **Robust Name Normalization**: Handles common punctuation/unicode mismatches (`:`, `*`, `·`, double spaces)
- **Docker Ready**: Includes Dockerfile for containerized deployment

## Requirements

- Python 3.11+
- Optional: Pillow (PIL) for PNG conversion; without it files are copied as-is
- Required packages (see handler requirements)

## Environment Variables

| Variable                   | Required | Default                   | Description                                                                |
| -------------------------- | -------- | ------------------------- | -------------------------------------------------------------------------- |
| `POSTERS_SOURCE_DIR`       | ❌       | `Posters`                 | Source directory containing downloaded assets                              |
| `ASSET_TARGET_DIR`         | ❌       | `../../config/assets`     | Target directory for organized assets (resolves to `kometa/config/assets`) |
| `ASSET_FORCE_PNG`          | ❌       | `True`                    | Convert all images to PNG format                                           |
| `ASSET_EXCEPTION_MAPPINGS` | ❌       | `exception_mappings.json` | Path to exception mappings configuration file                              |

Notes:

- Relative `--source`, `--target`, and `--exception-mappings` paths are resolved from the script directory first, then project root.
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

### Exception Mappings

The `exception_mappings.json` file handles special cases where title formatting doesn't match standard patterns:

```json
{
  "The Movie Title": "Movie Title",
  "Special Collection Name": "collection_name"
}
```

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

### Current Status

- Posters supported today
- Overlays/Backgrounds/Thumbnails can be added by subclassing `Organizer`

**Future handlers** can be added following the same pattern:

- Overlay Handler
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
- **Extensible**: New handlers can be added by subclassing the `Organizer` base class
- **Error Handling**: Comprehensive logging and exception mapping for non-standard titles
- **Dry-run Support**: Test changes before applying them with `--dry-run` flag
- **Type Safety**: Uses Python type hints throughout for better IDE support
- **Testing**: Full pytest test suite with coverage reporting

## License

Part of the Ortflix project
