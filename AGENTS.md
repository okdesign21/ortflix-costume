# Agent instructions (Kometa / Plex stack)

**Scope:** this file is the project-specific agent guide at the root of the `ortflix-costume` repository. The sibling `homeserver/AGENTS.md` contains shared rules for the multi-root workspace; follow both when working in this repository, with this file controlling Kometa-specific details.

**Workspace layout:** `homeserver/` is the coordination hub and workspace file; `ortflix`, `ortflix-costume`, and `ortflix-integrations-bot` are separate sibling repositories. Keep changes in their owning repository. No root-level symlink to this file is needed.

**Cursor:** the repository-local `.cursor/rules/kometa.mdc` imports this file with `@AGENTS.md`. Edit this file for project guidance; keep the Cursor rule as a short include rather than duplicating this content.

**Upstream (do not guess — read or cite):**

- Docs: [kometa.wiki](https://kometa.wiki/en/latest/)
- Repo: [Kometa-Team/Kometa](https://github.com/Kometa-Team/Kometa)

---

## Kometa: layout, config, and sync

### Project layout

The multi-root workspace is organized as sibling repositories:

```
server/
├── homeserver/                       # coordination hub and workspace file
│   ├── AGENTS.md                     # shared workspace rules
│   ├── meta.log                      # pulled Kometa run log (ignored by *.log)
│   ├── Films_report.yml              # pulled Films report (gitignored)
│   ├── TV Programmes_report.yml      # pulled TV report (gitignored)
│   └── Musicals_report.yml           # pulled Musicals report (gitignored)
├── ortflix/                          # server stack and deployment
├── ortflix-costume/                  # this repository; Kometa configuration
│   ├── AGENTS.md                     # project-specific guidance
│   ├── kometa/
│   │   └── config/                   # Kometa YAML, assets, and overlays
│   └── scripts/
└── ortflix-integrations-bot/         # integrations and automation
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
│   └── organizer/                   # personal title mappings and local runtime data
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

**Asset folder naming:** Kometa matches by the **exact Plex title**. With `asset_depth: 2` the expected path is `assets/<Category>/<PlexTitle>/poster.png`. Ignore missing-asset warnings only when no corresponding custom asset exists. When an asset exists with a different spelling or year, rename its folder or update `kometa/organizer/exception_mappings.json`. Set `ASSET_RESOLVER_TV_OMIT_YEAR=1` in the separate organizer to omit years on new TMDb TV resolutions. `dimensional_asset_rename` only renames image files inside matched folders; it does not map Plex titles to folder names.

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

- **Compose:** sibling repo [automation.yml](../ortflix/compose/automation.yml), included by [compose.yaml](../ortflix/compose/compose.yaml) — `kometa` service mounts **`mbdlist_api_key`** and the entrypoint exports **`KOMETA_MDBLISTAPIKEY`** together with Plex / TMDb / Tautulli (same block as the other keys).
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
| `-kl` | Pull logs **from** server | `/opt/kometa/config/*report*` + `logs/meta.log` → current dir |

No flags = all of `-k -a -o`.

**Usage:**

```bash
./scripts/sync_to_host.sh sync           # push everything
./scripts/sync_to_host.sh sync -k -a     # push YAML + assets only
./scripts/sync_to_host.sh sync-dry       # dry run
./scripts/sync_to_host.sh sync -kl       # pull logs/reports down
./scripts/sync_to_host.sh check          # validate all YAML locally
```

**Connection env:** `ORTFLIX_SYNC_HOST`, `ORTFLIX_SYNC_USER` (default: whoami), `ORTFLIX_SYNC_PORT` (default: 22). Can live in `scripts/.env`.

**`ORTFLIX_RSYNC_DELETE=1`** enables `--delete` on YAML/assets/overlays syncs — use with care.

**Server paths:** Kometa runs in Docker/k3s, config mounted at `/opt/kometa/config` (maps to `/config` inside container).

### Reports and logs

After a run, pull with `sync_to_host.sh sync -kl` from the `homeserver` hub folder. The files land there; `meta.log` is ignored by the hub's `*.log` rule, and the three report files have explicit hub `.gitignore` entries:

- `meta.log` — full Kometa run log; check **Error Summary** and **Warning Summary** sections at the end
- `Films_report.yml` — per-item report for Films library (TMDb IDs, titles, filter results)
- `TV Programmes_report.yml` — same for TV
- `Musicals_report.yml` — same for Musicals

**Reading the log:** errors appear at `[ERROR]` level inline, then are aggregated in the final `Error Summary` block. Warnings are in `Warning Summary`. Asset warnings are INFO-level and high volume: safe to ignore unless a matching custom asset already exists under `config/assets/` (see **Asset folder naming** above).

---

## Kometa: asset organizer tool

Reusable tooling lives in the private sibling repository
[`kometa-assets-organizer`](https://github.com/okdesign21/kometa-assets-organizer).
It owns the organizer package, tests, report validator, and holiday updater.
Do not copy its implementation back into this repository.

Use the shared `homeserver/.venv` and `python -m kometa_assets_organizer`.
The [README](README.md#kometa-tools-local) has commands wired to this repo's
personal asset targets, title mappings, and Plex library names.

Paths resolve from the caller's current directory. Export credentials/settings
explicitly; the tool no longer loads costume `.env` files or derives Plex URLs
from `ORTFLIX_SYNC_HOST`. Personal mappings live in
`kometa/organizer/exception_mappings.json`; caches and source downloads alongside
them are ignored. Organized assets and overlays stay under `kometa/config`.

The holiday updater runs from the new repo's `scripts/` directory with a
required `--config` pointing to `kometa/config/israeli_holidays.yml`. Use
`--dry-run` first. HTTPS verification is enabled by default.

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

Edit **this repository's `AGENTS.md` file** for Kometa facts and policy. The repository-local Cursor rule at **`.cursor/rules/kometa.mdc`** should only `@`-include this file; do not fork long prose into `.mdc` files or it will drift.
