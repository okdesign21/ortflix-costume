# Ortflix Costume

[![Lint - Ortflix Costume](https://github.com/okdesign21/ortflix-costume/actions/workflows/lint.yml/badge.svg)](https://github.com/okdesign21/ortflix-costume/actions/workflows/lint.yml)
[![Security - Ortflix Costume](https://github.com/okdesign21/ortflix-costume/actions/workflows/security.yml/badge.svg)](https://github.com/okdesign21/ortflix-costume/actions/workflows/security.yml)

Automation repository for Ortflix media customization:

- `kometa/` — assets, collection config, and tooling
- `tautulli/` — notification and tagging scripts
- `radarr/` — custom script hooks
- `scripts/` — host sync and operational utilities

## Repository Structure

- `kometa/config/` — Kometa collection and metadata config (YAML)
- `kometa/tools/asset-organizer/` — Kometa assets organizer Python package
- `kometa/tools/check_plex_titles.py` — compare Plex titles against asset folders
- `kometa/tools/update_jewish_dates.py` — refresh Israeli holiday schedule windows via HebCal API
- `radarr/` — Radarr custom script hooks (audio language fix, Overseerr requester tagging)
- `tautulli/` — Tautulli automation scripts (recently-added and watched tagging)
- `scripts/sync_to_host.sh` — rsync config, scripts, and assets to the host server

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
