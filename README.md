# Ortflix Costume

[![Lint - Ortflix Costume](https://github.com/okdesign21/ortflix-costume/actions/workflows/lint.yml/badge.svg)](https://github.com/okdesign21/ortflix-costume/actions/workflows/lint.yml)
[![Security - Ortflix Costume](https://github.com/okdesign21/ortflix-costume/actions/workflows/security.yml/badge.svg)](https://github.com/okdesign21/ortflix-costume/actions/workflows/security.yml)

Automation repository for Ortflix media customization:

**AI / agent / contributor guide:** [`AGENTS.md`](./AGENTS.md) (Kometa layout, sync, asset organizer, gotchas). The repository-local `.cursor/rules/kometa.mdc` loads this guide; shared workspace rules live in the sibling `homeserver/AGENTS.md`.

- `kometa/` — assets, collection config, and tooling
- `scripts/` — host sync and operational utilities

## Repository Structure

- `kometa/config/` — Kometa collection and metadata config (YAML)
- `kometa/tools/asset-organizer/` — Kometa assets organizer Python package
- `kometa/tools/update_jewish_dates.py` — refresh Israeli holiday schedule windows via HebCal API
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

### Kometa Assets Organizer (local)

```bash
cd kometa/tools/asset-organizer
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev,test]
pytest
```

## CI/CD

- `lint.yml` — Ruff, yamllint, ShellCheck, hadolint
- `security.yml` — TruffleHog and Trivy scans

This repository does **not** publish GitHub releases.

## Related Repositories

- Main stack: [`ortflix`](https://github.com/okdesign21/ortflix)
- Telegram bot and releases: [`ortflix-telegram`](https://github.com/okdesign21/ortflix-telegram)

## License

MIT. See [`LICENSE`](LICENSE).
