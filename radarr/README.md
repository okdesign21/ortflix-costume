# Radarr Scripts

Custom scripts for Radarr's **Connect → Custom Script** integration.

All scripts live in the Radarr container and are wired via:
**Radarr → Settings → Connect → + → Custom Script**

---

## Scripts

### `fix_audio_lang.py`

Fixes missing/`und` audio language tags on imported movie files.

**Why**: MP4 and MKV files from many release groups don't set a language tag inside
the container. Plex reads from the container (not from Radarr's metadata), so it
shows "Unknown" audio language. This script patches the tag at import time so Plex
sees it correctly from day one.

**Trigger**: On Import ✓ · On Upgrade ✓

**What it does**:
1. Reads `radarr_moviefile_path` from Radarr's env
2. Checks if any audio stream has a missing / `und` language tag
3. Detects the correct language from the filename (keyword lookup table)
4. Patches the tag in-place via `mkvpropedit` (MKV) or `ffmpeg` stream-copy (MP4)
5. Triggers Plex to re-analyze just that item

**Server requirements** (install once):
```bash
sudo apt install mkvtoolnix ffmpeg
```

**Radarr Connect settings**:
| Field | Value |
|---|---|
| Name | Fix Audio Language |
| Path | `/path/to/fix_audio_lang.py` |
| On Import | ✓ |
| On Upgrade | ✓ |

**Environment variables** (set in Radarr container):
| Var | Required | Default |
|---|---|---|
| `PLEX_URL` | no | `http://localhost:32400` |
| `PLEX_TOKEN` | no | reads `~/docker_secrets/plex_token` |
| `PLEX_MOVIES_SECTION` | no | `1` |

Can also be used as a one-off bulk fixer:
```bash
python3 fix_audio_lang.py           # dry run — shows what would change
python3 fix_audio_lang.py --apply   # apply to all files in MOVIES_DIR
```

---

### `tag_overseerr_requester.py`

Tags a newly imported movie in Radarr with who requested it in Overseerr.

**Replaces**: `tautulli/scripts/tag_radarr_recently_added.py`  
**Advantage**: fires at import (before Plex even sees the file), not after Plex "recently added".

**Trigger**: On Import ✓ · On Upgrade ✓

**What it does**:
1. Reads `radarr_movie_tmdbid` / `imdbid` / `title` / `year` from Radarr env
2. Looks up the movie in Radarr
3. Finds the matching Overseerr request
4. Tags the movie with `{requester}-requested` and `overseer`

**Environment variables** (set in Radarr container):
| Var | Required | Default |
|---|---|---|
| `RADARR_API_KEY` | ✓ | — |
| `RADARR_URL` | no | `http://radarr:7878` |
| `OVERSEERR_API_KEY` or `SEERR_API_KEY` | ✓ | — |
| `OVERSEERR_URL` or `SEERR_URL` | no | `http://seerr:5055` |

**Docker env example**:
```yaml
radarr:
  environment:
    - RADARR_API_KEY=${RADARR_API_KEY}
    - OVERSEERR_API_KEY=${OVERSEERR_API_KEY}
    - OVERSEERR_URL=http://seerr:5055
```

---

### `radarr_utils.py`

Shared utilities for all Radarr scripts (URL builders, session factories, Radarr/Overseerr API helpers).

Mirrors the relevant subset of `tautulli/scripts/tautulli_utils.py` for use in the
Radarr container (Docker containers can't import across each other's filesystems).

---

## Deployment

The Radarr config volume is mounted at `/opt/radarr` on the host → `/config` inside the container.

```bash
# Copy scripts to the persistent config volume (survives container restarts)
sudo cp radarr/scripts/*.py /opt/radarr/scripts/
```

In **Radarr → Settings → Connect → Custom Script**:
- `fix_audio_lang.py` → path: `/config/scripts/fix_audio_lang.py`
- `tag_overseerr_requester.py` → path: `/config/scripts/tag_overseerr_requester.py`

After adding scripts, redeploy Radarr to pick up the Telegram secrets:
```bash
docker compose up -d radarr
```

> **Note**: `radarr_utils.py` must be in the same directory (`/opt/radarr/scripts/`) as
> the scripts that import it.

## Environment variables

Injected automatically via Docker secrets (configured in `docker-compose-onelayer.yml`):

| Secret | Env var | Used by |
|---|---|---|
| `telegram_bot_token` | `TELEGRAM_BOT_TOKEN` | warning notifications |
| `telegram_chat_id` | `TELEGRAM_CHAT_ID` | warning notifications |
| `radarr_api_key` | `RADARR_API_KEY` | tag_overseerr_requester |
| `overseerr_api_key` | `OVERSEERR_API_KEY` | tag_overseerr_requester |
