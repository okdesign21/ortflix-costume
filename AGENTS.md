# Agent instructions (Kometa / Plex stack)

**Canonical copy (versioned):** this file at the **root of the `ortflix-costume` repository**. Any IDE or agent that reads `AGENTS.md` at repo root (Copilot, Codex, Claude Code, JetBrains, etc.) picks it up here.

**Multi-folder workspace:** if you use a parent folder (e.g. `myserver/`) that contains `ortflix-costume/` as a subfolder, some tools expect `AGENTS.md` at the workspace root — keep a **symlink** there pointing to `ortflix-costume/AGENTS.md`, or open the `ortflix-costume` folder as the workspace root.

**Cursor:** use **`ortflix-costume/.cursor/rules/kometa.mdc`** when this repo is the workspace root (`@AGENTS.md`). If the workspace root is a parent folder (e.g. `myserver/`), use **`.cursor/rules/kometa.mdc`** there with `@ortflix-costume/AGENTS.md` (or rely on the optional symlink `AGENTS.md` → `ortflix-costume/AGENTS.md` at the parent root).

**Upstream (do not guess — read or cite):**

- Docs: [kometa.wiki](https://kometa.wiki/en/latest/)
- Repo: [Kometa-Team/Kometa](https://github.com/Kometa-Team/Kometa)

---

## Kometa: layout, config, and sync

### Project layout

Typical layout when this repo lives under a parent `myserver/` workspace:

```
myserver/
├── meta.log                          # pulled from server — last Kometa run log
├── Films_report.yml                  # pulled from server — Films library report
├── TV Programmes_report.yml          # pulled from server — TV library report
├── Musicals_report.yml               # pulled from server — Musicals library report
└── ortflix-costume/                  # this repository
    ├── AGENTS.md                     # this file
    ├── kometa/
    │   ├── config/                   # ALL Kometa YAML config
    ...
```

Paths below are relative to **this repo root** (`ortflix-costume/`) unless stated otherwise.

```
ortflix-costume/
├── kometa/
│   ├── config/                       # ALL Kometa YAML config (source of truth on this Mac)
│   │   ├── config.yml                # main config: libraries, credentials refs, global settings
│   │   ├── collections.yml           # custom collections not covered by Kometa defaults
│   │   ├── franchises.yml            # franchise definitions — NOT wired into config.yml, does not run
│   │   ├── People.yml                # people collections (directors/actors)
│   │   ├── IMDBGenres.yml            # IMDB genre-based collections (scheduled weekly(sunday))
│   │   ├── stats.yml                 # stats/count-based collections for Films
│   │   ├── shows.yml                 # custom TV show collections
│   │   ├── musicals.yml              # Musicals library collections
│   │   ├── animation_disney.yml      # optional title bundles; not in config.yml by default (see file header)
│   │   ├── israeli_holidays.yml      # Israeli holiday seasonal collections
│   │   ├── tv_status_ribbons.yml     # TV status ribbon overlays (commented-out in config.yml)
│   │   ├── assets/                   # custom poster/artwork assets
│   │   │   ├── Companies/
│   │   │   ├── Genres/
│   │   │   ├── Movies_Shows/
│   │   │   └── People/
│   │   └── overlays/
│   │       └── Status/
│   └── tools/
│       └── asset-organizer/          # poster pipeline — see “Kometa: asset organizer tool” below
└── scripts/
    └── sync_to_host.sh               # rsync/ssh deploy to server
```

### Libraries

**Films (`type: movie`)**

- Overlays: `resolution`, `audio_codec`, `languages`, `mediastinger`
- Collections: `tautulli`, charts (`letterboxd`, `imdb`), `resolution`, `country`, `audio_language`, `commentary.yml`, `studio`, `People.yml`, awards, `franchise`, `universe`, `stats.yml`, `IMDBGenres.yml` (weekly), `based`, `seasonal`, `israeli_holidays.yml`, `collections.yml`; optional `animation_disney.yml` (not in `config.yml` by default)
- Operations: `assets_for_all: true`, `assets_for_all_collections: true`

**TV Programmes (`type: show`)**

- Overlays: `resolution`, `audio_codec`, `languages`, `mediastinger`
- Collections: `tautulli`, `shows.yml`, `audio_language`, `imdb`, `network`, `franchise`, `based`
- `tv_status_ribbons.yml` is commented out (present but inactive)
- Operations: `assets_for_all: true`, `assets_for_all_collections: true`

**Musicals (`type: movie`)**

- Collections only: `musicals.yml`
- No overlays

### config.yml key settings

```yaml
settings:
  asset_directory: [config/assets]
  asset_folders: true
  asset_depth: 2          # looks 2 levels deep: assets/<category>/<name>/poster.png
  create_asset_folders: false
  prioritize_assets: true
  dimensional_asset_rename: false
  overlay_artwork_filetype: webp_lossy
  overlay_artwork_quality: 90
  minimum_items: 2
  delete_below_minimum: true
```

**Asset folder naming:** Kometa matches by the **exact Plex title**. With `asset_depth: 2` the expected path is `assets/<Category>/<PlexTitle>/poster.png`. If Plex shows a title without year (e.g. "Friends") but the folder has year (e.g. `Friends (1994)/`), Kometa will warn "Unable to find asset folder". **Triage:** treat those log lines as noise when there is **no** corresponding folder anywhere under `kometa/config/assets/` (you never shipped a custom poster). If a folder **does** exist but uses a different spelling (common: Plex `Title` vs organizer/TMDb output `Title (YYYY)`), fix by **renaming** the asset folder to the Plex title, and/or add **`exception_mappings.json`** entries (same pattern as `Friends (1994)` → `Friends`). Optional: set `ASSET_RESOLVER_TV_OMIT_YEAR=1` when running `organize_assets.py` so TMDb TV resolutions omit the year in new folder names (movies still use `(year)`). For bulk TV renames already on disk, use `kometa/tools/asset-organizer/rename_tv_folders_to_plex.py` (Star Trek block today; extend the table for other shows). **`dimensional_asset_rename`** in Kometa `config.yml` only renames image files inside a matched folder by aspect ratio — it does **not** map Plex titles to folder names.

### Language overlay weights

Both `Films` and `TV Programmes` use `default: languages` with these explicit weights (all unique, no conflicts):

| Language | Weight |
|----------|--------|
| he       | 600    |
| en       | 590    |
| ja       | 580    |
| fr       | 570    |
| es       | 560    |
| de       | 550    |
| pt       | 540    |
| it       | 530    |
| nl       | 520    |
| ru       | 510    |
| ar       | 500    |
| hu       | 490    |
| pl       | 480    |

**Every language in the list must have an explicit unique weight.** If any are missing, items with multiple language tracks of the same weight will throw `Overlay Error: Overlays in a queue cannot have the same weight` and their overlay will be silently dropped.

Language position: `languages_horizontal_align: left`, `languages_vertical_align: bottom`, offsets 15/15.

### Credentials

Passed via environment variables (Docker secrets / `.env`); config.yml uses `<<PLACEHOLDER>>` syntax:
`<<PLEXURL>>`, `<<PLEXTOKEN>>`, `<<TMDBAPIKEY>>`, `<<TAUTULLIURL>>`, `<<TAUTULLIAPIKEY>>`, `<<MDBLISTAPIKEY>>`

Kometa builds `secret_args` from every non-empty `KOMETA_*` env var (`KOMETA_MDBLISTAPIKEY` → `<<MDBLISTAPIKEY>>`). If `KOMETA_MDBLISTAPIKEY` is missing or empty, you get **Config Error: mdblist sub-attribute apikey is blank** and MDBList **401**.

- **Compose:** sibling repo `ortflix/compose/docker-compose-onelayer.yml` — `kometa` service mounts **`mbdlist_api_key`** and the entrypoint exports **`KOMETA_MDBLISTAPIKEY`** together with Plex / TMDb / Tautulli (same block as the other keys).
- **Manual `docker exec`:** your shell snippet must include **the same four exports** as that entrypoint (including `mbdlist_api_key` → `KOMETA_MDBLISTAPIKEY`); otherwise only ad-hoc runs break while the container’s main process is fine.
- **K8s:** `kometa.yaml` expects `media-secrets` key **`mbdlist-api-key`**; ensure Infisical/sync populates it.

### Sync workflow

**Script:** `scripts/sync_to_host.sh`

**What it syncs (Mac → server over SSH/rsync):**

| Flag | What | Source → Destination |
|------|------|----------------------|
| `-k` | Kometa YAML (*.yml/*.yaml, no assets) | `kometa/config/` → `/opt/kometa/config/` |
| `-a` | Kometa assets (full tree) | `kometa/config/assets/` → `/opt/kometa/config/assets/` |
| `-o` | Kometa overlays | `kometa/config/overlays/` → `/opt/kometa/config/overlays/` |
| `-t` | Tautulli scripts | `tautulli/` → `/opt/tautulli/scripts/` |
| `-r` | Radarr scripts | `radarr/` → `/opt/radarr/scripts/` |
| `-kl` | Pull logs **from** server | `/opt/kometa/config/*report*` + `logs/meta.log` → current dir |

No flags = all of `-k -a -o -t -r`.

**Usage:**

```bash
./scripts/sync_to_host.sh sync           # push everything
./scripts/sync_to_host.sh sync -k -a     # push YAML + assets only
./scripts/sync_to_host.sh sync-dry       # dry run
./scripts/sync_to_host.sh sync -kl       # pull logs/reports down
./scripts/sync_to_host.sh sync -r        # Radarr scripts only
./scripts/sync_to_host.sh check          # validate all YAML locally
```

**Connection env:** `ORTFLIX_SYNC_HOST`, `ORTFLIX_SYNC_USER` (default: whoami), `ORTFLIX_SYNC_PORT` (default: 22). Can live in `scripts/.env`.

**`ORTFLIX_RSYNC_DELETE=1`** enables `--delete` on YAML/assets/overlays syncs — use with care.

**Python deps (Tautulli/Radarr):** `tautulli_utils.py` / `radarr_utils.py` run `python3 -m pip install --target /config/.pydeps` on first import if `requests` is missing (no init hooks, no extra compose volumes). Override with env `PY_DEPS_TARGET` if needed.

**Server paths:** Kometa runs in Docker/k3s, config mounted at `/opt/kometa/config` (maps to `/config` inside container).

### Reports and logs

After a run, pull with `sync_to_host.sh sync -kl`. Files land in the workspace root (often parent `myserver/` when using a monorepo folder):

- `meta.log` — full Kometa run log; check **Error Summary** and **Warning Summary** sections at the end
- `Films_report.yml` — per-item report for Films library (TMDb IDs, titles, filter results)
- `TV Programmes_report.yml` — same for TV
- `Musicals_report.yml` — same for Musicals

**Reading the log:** errors appear at `[ERROR]` level inline, then are aggregated in the final `Error Summary` block. Warnings are in `Warning Summary`. Asset warnings are INFO-level and high volume: safe to ignore unless a matching custom asset already exists under `config/assets/` (see **Asset folder naming** above).

---

## Kometa: asset organizer tool

**Entry point:** `kometa/tools/asset-organizer/organize_assets.py`

**What it does:** Takes downloaded posters from a source folder, normalises names, converts to PNG (Pillow), caps size at 10,480,000 bytes (Plex/Kometa limit), and places them into `config/assets/<Category>/<Name>/poster.png`.

**Modules:**

- `organize_assets.py` — CLI, arg parsing, env defaults, wires handlers together
- `handlers.py` — base `Organizer` class, image conversion, size-shrinking logic, `normalize_name()`, SHA-256 hash sidecar (`.poster_source_hash`) for incremental mode
- `poster_handler.py` — `PosterOrganizer`: handles Movies_Shows, People, Companies, Genres; strips role suffixes from people names; strips " Collection" suffix from franchise folder names to match Kometa's `remove_suffix: "Collection"` default
- `overlay_handler.py` — `OverlayOrganizer`: handles overlay PNGs → `config/overlays/`
- `tmdb_resolver.py` — last-resort TMDb API lookup for `Title (YYYY)` items; caches into `exception_mappings.json`
- `exception_mappings.json` — manual + auto-written name overrides (source → Kometa folder name)

**Asset categories:** `Companies`, `Genres`, `Movies_Shows`, `People`

**Name normalisation order:**

1. `exception_mappings.json` exact match
2. Standard rules: NFKC unicode, curly quotes → straight, `–`/`—` → `-`, `:` between digits → `-`, other `:` → ` -`, `*` → `-`, double space → ` & `
3. TMDb API (only for `Title (YYYY)` format, only when `TMDB_API_KEY` is set; writes result back to `exception_mappings.json`)

**Key CLI flags:**

- `--dry-run` — show what would happen, no writes
- `--full` — re-process everything, ignore hash sidecars
- `--force-png` / `--no-force-png` — convert to PNG (default: on)
- `--shrink-large-posters` — walk target and shrink existing oversized posters, then exit
- `--no-tmdb` — skip TMDb lookups (fast incremental runs)
- `--strip-collection-suffix` / `--no-strip-collection-suffix`
- `--source`, `--target`, `--overlays-source`, `--overlays-target`
- `--exception-mappings` — path to mappings JSON

**Env var defaults** (can also go in `kometa/.env`, `scripts/.env`, or repo-root `.env`):
`POSTERS_SOURCE_DIR`, `OVERLAYS_SOURCE_DIR`, `ASSET_TARGET_DIR`, `OVERLAY_TARGET_DIR`, `ASSET_FORCE_PNG`, `ASSET_EXCEPTION_MAPPINGS`, `ASSET_MAX_POSTER_BYTES`, `KOMETA_STRIP_COLLECTION_SUFFIX`, `TMDB_API_KEY`, `ASSET_RESOLVER_TV_OMIT_YEAR` (optional: `1` / `true` — TMDb **TV** hits omit `(year)` in output folder names to match Plex; default unchanged).

**One-off renames:** `kometa/tools/asset-organizer/rename_tv_folders_to_plex.py` renames on-disk `Movies_Shows` folders from TMDb-style `Show (YYYY)` to Plex-style titles for the Star Trek table inside the script (extend for other series).

---

## Kometa: known patterns and gotchas

- **`franchises.yml` is NOT included in `config.yml`** — it exists as a reference/staging file but does not run. `default: franchise` handles franchise collections automatically.
- **Duplicate collection warnings** (Spider-Man MCU, Before...) come from `collections.yml` colliding with what `default: franchise` auto-generates from TMDb. Fix by adding the TMDb franchise ID to the de-duplication fields on the right library’s `default: franchise` block: under **TV Programmes**, use `remove_data` in `template_variables` (same block as `append_addons` / `name_mapping_Star Trek`). Under **Films**, the parallel mechanism is `exclude` in `template_variables` on that library’s `default: franchise` entry — adjust whichever list that block already uses.
- **4K resolution errors** — if no 4K content exists in a library, `default: resolution` overlay will error with `No matches found with regex pattern (?i)2160`. Add `use_4K: false` to the resolution overlay `template_variables` to suppress.
- **`minimum_items: 2` + `delete_below_minimum: true`** — collections with fewer than 2 items are automatically removed. The Disney Live-Action Remakes collection will stay gone until those titles are in Plex.
- **Tautulli `list_minimum` warning** — `tautulli_popular`/`tautulli_watched` don't have `list_minimum` set in the template; Kometa uses 0 as default (harmless).
- **Letterboxd scraping** — may fail intermittently with "No List Items found"; Letterboxd blocks scrapers. Not a config issue.

---

## Editing convention

Edit **this `AGENTS.md` file** for facts and policy. Cursor rule stubs (**`ortflix-costume/.cursor/rules/kometa.mdc`** and, if used, **`<parent>/.cursor/rules/kometa.mdc`**) should only `@`-include this file; do not fork long prose into `.mdc` files or it will drift.
