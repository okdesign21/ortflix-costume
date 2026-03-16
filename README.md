# Ortflix Costume

[![Lint - Ortflix Costume](https://github.com/okdesign21/ortflix-costume/actions/workflows/lint.yml/badge.svg)](https://github.com/okdesign21/ortflix-costume/actions/workflows/lint.yml)
[![Security - Ortflix Costume](https://github.com/okdesign21/ortflix-costume/actions/workflows/security.yml/badge.svg)](https://github.com/okdesign21/ortflix-costume/actions/workflows/security.yml)

Automation repository for Ortflix media customization:

- `kometa/` assets and collection tooling
- `tautulli/` scripts and notification helpers

## Repository Structure

- `kometa/asset_helpers/Organize_Downloads/` — Kometa assets organizer Python package
- `kometa/config/` — Kometa collection and metadata config
- `tautulli/scripts/` — Tautulli automation scripts

## Quick Start

```bash
git clone https://github.com/okdesign21/ortflix-costume.git
cd ortflix-costume
```

### Kometa Assets Organizer (local)

```bash
cd kometa/asset_helpers/Organize_Downloads
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
