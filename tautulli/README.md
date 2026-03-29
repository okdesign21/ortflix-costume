# Tautulli Scripts

Automation scripts for Tautulli integrations with Radarr, Sonarr, and Overseerr.

## Scripts

### `tag_radarr_recently_added.py`

Tags recently-added movies in Radarr with the Overseerr requester information.

**Trigger**: Tautulli → Notify on Recently Added (Movies)

**What it does**:

1. Receives movie details from Tautulli (TMDb ID, IMDb ID, title, year)
1. Looks up the movie in Radarr (with fast-path tmdb/imdb lookup)
1. Finds the Overseerr request for that movie
1. Tags the movie with:
   - `{requester-username}-requested` (e.g., `john-requested`)
   - `overseer` (to mark it came through Overseerr)

**Performance**:

- **Fast-path lookup** (< 10s): Uses tmdb/imdb ID filter on Radarr API
- **Fallback** (< 20s): Fetches full movie list if IDs don't match
- **Overseerr query** (< 15s): Fetches up to 100 approved requests
- **Total**: Completes in ~15-30s (well under Tautulli's 30s timeout)

**Tautulli Configuration**:

```yaml
Notifications > Notifiers > Add
Type: Script
Name: Tag Radarr Recently Added
Description: Tags new movies with Overseerr requester info
Script: /config/scripts/tag_radarr_recently_added.py
Parameters: {theme movie_db} {imdb_id} {title} {year}
  (Arguments passed by Tautulli)
```

**Environment Variables** (set in docker-compose or .env):

- `RADARR_API_KEY` (required)
- `RADARR_URL` (optional, default: `http://radarr:7878`)
- `RADARR_HOST` (optional, default: `radarr`)
- `RADARR_PORT` (optional, default: `7878`)
- `OVERSEERR_API_KEY` or `SEERR_API_KEY` (required)
- `OVERSEERR_URL` or `SEERR_URL` (optional, default host: `seerr`, port: `5055`)
- `OVERSEERR_HOST` or `SEERR_HOST` (optional, default: `seerr`)
- `OVERSEERR_PORT` or `SEERR_PORT` (optional, default: `5055`)

**Docker Integration**:

```yaml
tautulli:
  environment:
    - RADARR_URL=http://radarr:7878
    - OVERSEERR_URL=http://seerr:5055
    - RADARR_API_KEY=${RADARR_API_KEY}
    - OVERSEERR_API_KEY=${OVERSEERR_API_KEY}
```

### `tag_radarr_watched.py`

(Optional) Tags movies in Radarr when watched via Plex

## Trigger

Tautulli → Notify on Watched (Movies)

## What it does

1. Tags the movie in Radarr with `watched`
1. Useful for tracking which requested movies have been watched

### `tautulli_utils.py`

Shared utilities for all Tautulli scripts

- **URL builders**: `radarr_base_url()`, `sonarr_base_url()`, `overseerr_base_url()`
- **Session factories**: Pre-configured requests.Session with API headers
- **Radarr/Sonarr helpers**: `find_movie()`, `find_series()`, `ensure_tag()`, `add_tags_to_movie()`
- **Discord support**: Optional Discord webhook posting

All helpers support Docker internal hostnames by default (e.g., `http://radarr:7878`).

## URL Configuration

URLs are resolved in this order:

1. **Explicit env var** (highest priority)

   - `RADARR_URL=http://custom.radarr:7878`

1. **Host:Port env vars**

   - `RADARR_HOST=radarr` + `RADARR_PORT=7878` → `http://radarr:7878`

1. **Default Docker hostnames** (lowest priority)

   - Radarr: `http://radarr:7878`
   - Sonarr: `http://sonarr:8989`
   - Overseerr: `http://overseerr:5055`

**Docker Network**:

All services on the same Docker network, use internal hostnames:

```yaml
# docker-compose-onelayer.yml
services:
  radarr:
    hostname: radarrDocker
    # accessible as http://radarr:7878 from Tautulli

  sonarr:
    hostname: sonarrDocker
    # accessible as http://sonarr:8989 from Tautulli

  overseerr:
    hostname: overseerrDocker
    # accessible as http://overseerr:5055 from Tautulli

  tautulli:
    environment:
      RADARR_URL: http://radarr:7878
      SONARR_URL: http://sonarr:8989
      OVERSEERR_URL: http://overseerr:5055
```

## Running Locally

For testing the scripts on your machine (not in Docker):

```bash
cd tautulli/scripts

# Set environment variables
export RADARR_API_KEY=your_key
export OVERSEERR_API_KEY=your_key
export RADARR_URL=http://localhost:7878
export OVERSEERR_URL=http://localhost:5055

# Test tag_radarr_recently_added.py
python3 tag_radarr_recently_added.py \
  --themoviedb_id 11878 \
  --imdb_id tt0055630 \
  --title "Yojimbo" \
  --year 1961
```

## Debugging

### Enable debug logging

```bash
# In Tautulli, set script output to verbose
# Check Tautulli logs:
docker logs tautulli | grep "tag_radarr"
```

### Test API connectivity

```bash
# Radarr
curl -H "X-Api-Key: $RADARR_API_KEY" http://radarr:7878/api/v3/movie | head -c 100

# Overseerr
curl -H "X-Api-Key: $OVERSEERR_API_KEY" http://overseerr:5055/api/v1/request | head -c 100
```

### Common issues

#### Timeout (Script exceeded timeout limit of 30 seconds)

- Radarr/Overseerr API is slow or unreachable
- Network connectivity issue between Tautulli and services
- API keys have insufficient permissions (causes retries)

#### No matching movie in Radarr

- Movie not yet added to Radarr
- Title/year mismatch between Plex and Radarr
- TMDb/IMDb ID mismatch

#### Tag creation failed

- Radarr API key lacks write permissions
- Check Radarr settings > General > Enable Authentication

## Integration with Telegram Bot

The scripts work seamlessly with the Telegram bot:

1. **Plex adds movie** → Tautulli triggers
1. **tag_radarr_recently_added.py runs** → Looks up Overseerr requester
1. **Tags movie in Radarr** → Requester's name is now tagged
1. **Movie downloads** → Radarr notifies via webhook
1. **Telegram bot receives webhook** → Sends notification to user

All via Docker internal network, no external calls needed.

## License

Part of the Ortflix project
