# Ortflix Costume

[![Lint - Ortflix Costume](https://github.com/okdesign21/ortflix-costume/actions/workflows/lint.yml/badge.svg)](https://github.com/okdesign21/ortflix-costume/actions/workflows/lint.yml)
[![Security - Ortflix Costume](https://github.com/okdesign21/ortflix-costume/actions/workflows/security.yml/badge.svg)](https://github.com/okdesign21/ortflix-costume/actions/workflows/security.yml)

Personal configuration repository for Ortflix media customization:

**AI / agent / contributor guide:** [`AGENTS.md`](./AGENTS.md) (Kometa layout, sync, asset organizer, gotchas). The repository-local `.cursor/rules/kometa.mdc` loads this guide; shared workspace rules live in the sibling `homeserver/AGENTS.md`.

- `kometa/` — assets, collection config, and personal organizer settings
- `scripts/` — host sync and operational utilities

## Repository Structure

- `kometa/config/` — Kometa collection and metadata config (YAML)
- `kometa/organizer/exception_mappings.json` — personal title overrides
- Reusable organizer and holiday updater:
  [`kometa-assets-organizer`](https://github.com/okdesign21/kometa-assets-organizer)
  (private; clone as a sibling repository)
- `scripts/sync_to_host.sh` — rsync config, scripts, and assets to the host server
- `ortflix-telegram/scripts/check_plex_titles.py` — compare Plex library items to Kometa asset folders

### Sync preview

Run `bash scripts/sync_to_host.sh sync-dry` (alias: `dry-run`) to preview
transfers without creating remote directories or writing/deleting transferred
files. Selectors `-k`, `-a`, `-o`, and `-kl` work as with `sync`, including
deletion previews when `ORTFLIX_RSYNC_DELETE=1`.

Preview still requires SSH access and rsync on both ends. Missing remote parent
directories may cause rsync to fail; create them explicitly or use normal `sync`
when ready to apply changes. Normal `sync`/`rsync` still creates the selected
destination directories before transferring files.

Run the offline sync regression checks with:

```bash
bash scripts/tests/sync_to_host_test.sh
```

## Quick Start

```bash
git clone https://github.com/okdesign21/ortflix-costume.git
cd ortflix-costume
```

### Kometa tools (local)

Reusable Python code now lives in `kometa-assets-organizer`; personal
collections, assets, and mappings stay here. Use the shared
`homeserver/.venv` for this workspace. From this repository on Windows:

```powershell
..\homeserver\.venv\Scripts\python.exe -m pip install -e "..\kometa-assets-organizer[plex,scripts,test,dev]"
..\homeserver\.venv\Scripts\python.exe -m kometa_assets_organizer --source kometa\organizer\Posters --target kometa\config\assets --overlays-source kometa\organizer\Overlays --overlays-target kometa\config\overlays --exception-mappings kometa\organizer\exception_mappings.json --plex-libraries "Films,TV Programmes" --plex-index-cache kometa\organizer\plex_index_cache.json --match-review-output kometa\organizer\match_review.json --dry-run
..\homeserver\.venv\Scripts\python.exe ..\kometa-assets-organizer\scripts\update_jewish_dates.py --config kometa\config\israeli_holidays.yml --year 2027 --dry-run
```

Remove `--dry-run` after reviewing the preview. Poster/overlay input directories
are local downloads, not tool source. If you have existing local inputs or
lookup snapshots under the old `kometa/tools/asset-organizer` directory, move
them into `kometa/organizer` or pass their absolute paths explicitly.
The existing personal mappings and TMDb cache have moved to that directory;
the cache is now ignored. The new tool resolves relative paths from the
current directory and does not auto-load the old costume `.env` locations.
Export Plex/TMDb settings explicitly, including `KOMETA_PLEXURL` (the
`ORTFLIX_SYNC_HOST` fallback no longer applies). The holiday updater verifies
HTTPS certificates; use `REQUESTS_CA_BUNDLE` for a trusted custom CA.

## CI/CD

- `lint.yml` — Ruff, yamllint, ShellCheck, hadolint
- `security.yml` — TruffleHog and Trivy scans

This repository does **not** publish GitHub releases.

## Related Repositories

- Main stack: [`ortflix`](https://github.com/okdesign21/ortflix)
- Telegram bot and releases: [`ortflix-telegram`](https://github.com/okdesign21/ortflix-telegram)

## License

MIT. See [`LICENSE`](LICENSE).
