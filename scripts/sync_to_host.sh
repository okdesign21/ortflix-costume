#!/usr/bin/env bash
# Sync ortflix-costume content to a host over SSH/rsync (matches Ansible k3s paths).
#
# Connection (env or prompt if unset):
#   ORTFLIX_SYNC_HOST
#   ORTFLIX_SYNC_USER   (default: current user)
#   ORTFLIX_SYNC_PORT   (default: 22)
#
# What syncs (sync / sync-dry):
#   -k  Kometa YAML only: kometa/config/**/*.yml,*.yaml → /opt/kometa/config
#   -a  Kometa assets: kometa/config/assets/ → /opt/kometa/config/assets (full tree)
#   -o  Kometa overlays: kometa/config/overlays/ → /opt/kometa/config/overlays (full tree)
#   -t  Tautulli: tautulli *.py + requirements.txt → /opt/tautulli/scripts
#   -r  Radarr: radarr *.py + requirements.txt → /opt/radarr/scripts
#   -kl Pull Kometa logs/reports from host → current directory (download only)
#   If none of -k -a -o -t -r are given, all five run (excludes -kl).
#
# Optional:
#   ORTFLIX_RSYNC_DELETE=1 — rsync --delete (Kometa YAML + assets + overlays; use with care)
#   KOMETA_CONFIG_SRC, KOMETA_ASSETS_SRC, KOMETA_OVERLAYS_SRC, TAUTULLI_SCRIPTS_SRC, RADARR_SCRIPTS_SRC
#   KOMETA_CONFIG_DEST, KOMETA_ASSETS_DEST, KOMETA_OVERLAYS_DEST, TAUTULLI_SCRIPTS_DEST, RADARR_SCRIPTS_DEST
#
# Defaults file (optional): scripts/.env.sync — KEY=value lines, # comments.
#   Path override: SYNC_ENV_FILE=/path/to/file
#   Only variables that are unset before running this script are applied (your shell
#   exports and ORTFLIX_SYNC_HOST=ip ./sync_to_host.sh still win).
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COSTUME_ROOT="$(dirname "$SCRIPT_DIR")"

# shellcheck disable=SC1091
load_env_sync_defaults() {
  local f="${SYNC_ENV_FILE:-$SCRIPT_DIR/.env.sync}"
  [[ -f "$f" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ -z "${line// }" ]] && continue
    case "$line" in
      *=*) ;;
      *) continue ;;
    esac
    local key="${line%%=*}"
    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"
    local val="${line#*=}"
    val="${val#"${val%%[![:space:]]*}"}"
    val="${val%"${val##*[![:space:]]}"}"
    if [[ "$val" =~ ^\".*\"$ ]]; then
      val="${val#\"}"
      val="${val%\"}"
    elif [[ "$val" =~ ^\'.*\'$ ]]; then
      val="${val#\'}"
      val="${val%\'}"
    fi
    [[ -z "$key" ]] && continue
    if [[ -z "${!key+x}" ]]; then
      export "$key=$val"
    fi
  done <"$f"
}

load_env_sync_defaults

KOMETA_CONFIG_SRC="${KOMETA_CONFIG_SRC:-$COSTUME_ROOT/kometa/config}"
KOMETA_ASSETS_SRC="${KOMETA_ASSETS_SRC:-$KOMETA_CONFIG_SRC/assets}"
KOMETA_OVERLAYS_SRC="${KOMETA_OVERLAYS_SRC:-$KOMETA_CONFIG_SRC/overlays}"
TAUTULLI_SCRIPTS_SRC="${TAUTULLI_SCRIPTS_SRC:-$COSTUME_ROOT/tautulli}"
RADARR_SCRIPTS_SRC="${RADARR_SCRIPTS_SRC:-$COSTUME_ROOT/radarr}"

KOMETA_CONFIG_DEST="${KOMETA_CONFIG_DEST:-/opt/kometa/config}"
KOMETA_ASSETS_DEST="${KOMETA_ASSETS_DEST:-/opt/kometa/config/assets}"
KOMETA_OVERLAYS_DEST="${KOMETA_OVERLAYS_DEST:-/opt/kometa/config/overlays}"
TAUTULLI_SCRIPTS_DEST="${TAUTULLI_SCRIPTS_DEST:-/opt/tautulli/scripts}"
RADARR_SCRIPTS_DEST="${RADARR_SCRIPTS_DEST:-/opt/radarr/scripts}"

die() {
  echo "Error: $*" >&2
  exit 1
}

usage() {
  cat <<EOF
Usage: $(basename "$0") <command> [flags]

Commands:
  check       Validate YAML under kometa/config (Python+PyYAML or Ruby)
  paths       Print resolved paths and remote destinations
  sync        Rsync (see flags below)
  sync-dry    Same as sync with --dry-run
  rsync       Alias for sync
  dry-run     Alias for sync-dry
  ansible     ansible-playbook --tags kometa-sync,tautulli-sync (optional)

sync / sync-dry flags (default if none: -k -a -o -t -r):
  -k          Kometa config (*.yml, *.yaml only)
  -a          Kometa assets (kometa/config/assets → server .../config/assets)
  -o          Kometa overlays (kometa/config/overlays → server .../config/overlays)
  -t          Tautulli scripts (*.py + requirements.txt)
  -r          Radarr scripts (*.py + requirements.txt)
  -kl         Pull Kometa logs from server → current directory
                  *report* files from /opt/kometa/config/
                  logs/meta.log from /opt/kometa/config/logs/

Examples:
  $(basename "$0") sync
  $(basename "$0") sync -k -a
  $(basename "$0") sync-dry -t
  $(basename "$0") sync -r

Environment:
  ORTFLIX_SYNC_HOST, ORTFLIX_SYNC_USER, ORTFLIX_SYNC_PORT — if HOST is unset, you will be prompted.
  SYNC_ENV_FILE — optional path to defaults file (default: scripts/.env.sync next to this script).
EOF
}

resolve_connection() {
  if [[ -z "${ORTFLIX_SYNC_HOST:-}" ]]; then
    read -r -p "SSH host (IP or hostname): " ORTFLIX_SYNC_HOST
    [[ -n "${ORTFLIX_SYNC_HOST// }" ]] || die "Host is required"
  fi
  if [[ -z "${ORTFLIX_SYNC_USER:-}" ]]; then
    local def
    def="$(whoami)"
    read -r -p "SSH user [${def}]: " ORTFLIX_SYNC_USER
    ORTFLIX_SYNC_USER=${ORTFLIX_SYNC_USER:-$def}
  fi
  ORTFLIX_SYNC_PORT="${ORTFLIX_SYNC_PORT:-22}"
}

ssh_ortflix() {
  local port="${ORTFLIX_SYNC_PORT:-22}"
  if [[ "$port" == "22" ]]; then
    ssh -o StrictHostKeyChecking=accept-new "$@"
  else
    ssh -p"$port" -o StrictHostKeyChecking=accept-new "$@"
  fi
}

rsync_rsh() {
  local port="${ORTFLIX_SYNC_PORT:-22}"
  if [[ "$port" == "22" ]]; then
    echo "ssh -o StrictHostKeyChecking=accept-new"
  else
    echo "ssh -p${port} -o StrictHostKeyChecking=accept-new"
  fi
}

remote_target() {
  local path="$1"
  echo "${ORTFLIX_SYNC_USER}@${ORTFLIX_SYNC_HOST}:${path}"
}

parse_sync_selectors() {
  SYNC_K=0
  SYNC_A=0
  SYNC_O=0
  SYNC_T=0
  SYNC_R=0
  SYNC_KL=0
  local arg
  for arg in "$@"; do
    case "$arg" in
      -k)  SYNC_K=1  ;;
      -a)  SYNC_A=1  ;;
      -o)  SYNC_O=1  ;;
      -t)  SYNC_T=1  ;;
      -r)  SYNC_R=1  ;;
      -kl) SYNC_KL=1 ;;
      *) die "Unknown flag: $arg (use -k, -a, -o, -t, -r, -kl)" ;;
    esac
  done
  if [[ $((SYNC_K + SYNC_A + SYNC_O + SYNC_T + SYNC_R + SYNC_KL)) -eq 0 ]]; then
    SYNC_K=1
    SYNC_A=1
    SYNC_O=1
    SYNC_T=1
    SYNC_R=1
  fi
}

rsync_kometa_yaml() {
  local dry="${1:-0}"
  [[ -d "$KOMETA_CONFIG_SRC" ]] || die "Missing directory: $KOMETA_CONFIG_SRC"
  local -a args=(-avz)
  [[ "$dry" == "1" ]] && args+=(--dry-run)
  [[ "${ORTFLIX_RSYNC_DELETE:-0}" == "1" ]] && args+=(--delete)
  args+=(
    --exclude='assets/***'
    --include='*/'
    --include='*.yml'
    --include='*.yaml'
    --exclude='*'
  )
  args+=(-e "$(rsync_rsh)" "$KOMETA_CONFIG_SRC/" "$(remote_target "$KOMETA_CONFIG_DEST")/")
  echo "→ Kometa YAML: ${KOMETA_CONFIG_SRC}/ → ${ORTFLIX_SYNC_HOST}:${KOMETA_CONFIG_DEST}/"
  rsync "${args[@]}"
}

rsync_kometa_assets() {
  local dry="${1:-0}"
  [[ -d "$KOMETA_ASSETS_SRC" ]] || {
    echo "(skip) Kometa assets: no local folder $KOMETA_ASSETS_SRC"
    return 0
  }
  local -a args=(-avz)
  [[ "$dry" == "1" ]] && args+=(--dry-run)
  [[ "${ORTFLIX_RSYNC_DELETE:-0}" == "1" ]] && args+=(--delete)
  args+=(-e "$(rsync_rsh)" "$KOMETA_ASSETS_SRC/" "$(remote_target "$KOMETA_ASSETS_DEST")/")
  echo "→ Kometa assets: ${KOMETA_ASSETS_SRC}/ → ${ORTFLIX_SYNC_HOST}:${KOMETA_ASSETS_DEST}/"
  rsync "${args[@]}"
}

rsync_kometa_overlays() {
  local dry="${1:-0}"
  [[ -d "$KOMETA_OVERLAYS_SRC" ]] || {
    echo "(skip) Kometa overlays: no local folder $KOMETA_OVERLAYS_SRC"
    return 0
  }
  local -a args=(-avz)
  [[ "$dry" == "1" ]] && args+=(--dry-run)
  [[ "${ORTFLIX_RSYNC_DELETE:-0}" == "1" ]] && args+=(--delete)
  args+=(-e "$(rsync_rsh)" "$KOMETA_OVERLAYS_SRC/" "$(remote_target "$KOMETA_OVERLAYS_DEST")/")
  echo "→ Kometa overlays: ${KOMETA_OVERLAYS_SRC}/ → ${ORTFLIX_SYNC_HOST}:${KOMETA_OVERLAYS_DEST}/"
  rsync "${args[@]}"
}

rsync_tautulli_scripts() {
  local dry="${1:-0}"
  [[ -d "$TAUTULLI_SCRIPTS_SRC" ]] || die "Missing directory: $TAUTULLI_SCRIPTS_SRC"
  local -a args=(-avz)
  [[ "$dry" == "1" ]] && args+=(--dry-run)
  args+=(
    --include='*/'
    --include='*.py'
    --include='requirements.txt'
    --exclude='*'
  )
  args+=(-e "$(rsync_rsh)" "$TAUTULLI_SCRIPTS_SRC/" "$(remote_target "$TAUTULLI_SCRIPTS_DEST")/")
  echo "→ Tautulli scripts: ${TAUTULLI_SCRIPTS_SRC}/ → ${ORTFLIX_SYNC_HOST}:${TAUTULLI_SCRIPTS_DEST}/"
  rsync "${args[@]}"
}

rsync_radarr_scripts() {
  local dry="${1:-0}"
  [[ -d "$RADARR_SCRIPTS_SRC" ]] || die "Missing directory: $RADARR_SCRIPTS_SRC"
  local -a args=(-avz)
  [[ "$dry" == "1" ]] && args+=(--dry-run)
  args+=(
    --include='*/'
    --include='*.py'
    --include='requirements.txt'
    --exclude='*'
  )
  args+=(-e "$(rsync_rsh)" "$RADARR_SCRIPTS_SRC/" "$(remote_target "$RADARR_SCRIPTS_DEST")/")
  echo "→ Radarr scripts: ${RADARR_SCRIPTS_SRC}/ → ${ORTFLIX_SYNC_HOST}:${RADARR_SCRIPTS_DEST}/"
  rsync "${args[@]}"
}

rsync_kometa_logs() {
  local dry="${1:-0}"
  local -a args=(-av)
  [[ "$dry" == "1" ]] && args+=(--dry-run)
  args+=(-e "$(rsync_rsh)")
  echo "↓ Kometa reports: ${ORTFLIX_SYNC_HOST}:${KOMETA_CONFIG_DEST}/*report* → ."
  rsync "${args[@]}" "${ORTFLIX_SYNC_USER}@${ORTFLIX_SYNC_HOST}:${KOMETA_CONFIG_DEST}/*report*" .
  echo "↓ Kometa meta.log: ${ORTFLIX_SYNC_HOST}:${KOMETA_CONFIG_DEST}/logs/meta.log → ."
  rsync "${args[@]}" "${ORTFLIX_SYNC_USER}@${ORTFLIX_SYNC_HOST}:${KOMETA_CONFIG_DEST}/logs/meta.log" .
}

ensure_remote_dirs() {
  local -a paths=()
  [[ "$SYNC_K" == "1" ]] && paths+=("$KOMETA_CONFIG_DEST")
  [[ "$SYNC_A" == "1" ]] && paths+=("$KOMETA_ASSETS_DEST")
  [[ "$SYNC_O" == "1" ]] && paths+=("$KOMETA_OVERLAYS_DEST")
  [[ "$SYNC_T" == "1" ]] && paths+=("$TAUTULLI_SCRIPTS_DEST")
  [[ "$SYNC_R" == "1" ]] && paths+=("$RADARR_SCRIPTS_DEST")
  [[ ${#paths[@]} -eq 0 ]] && return 0
  local joined
  joined=$(printf ' %q' "${paths[@]}")
  ssh_ortflix "${ORTFLIX_SYNC_USER}@${ORTFLIX_SYNC_HOST}" "mkdir -p${joined}"
}

cmd_sync() {
  local dry="${1:?}"
  shift
  parse_sync_selectors "$@"
  resolve_connection
  ensure_remote_dirs
  [[ "$SYNC_K"  == "1" ]] && rsync_kometa_yaml "$dry"
  [[ "$SYNC_A"  == "1" ]] && rsync_kometa_assets "$dry"
  [[ "$SYNC_O"  == "1" ]] && rsync_kometa_overlays "$dry"
  [[ "$SYNC_T"  == "1" ]] && rsync_tautulli_scripts "$dry"
  [[ "$SYNC_R"  == "1" ]] && rsync_radarr_scripts "$dry"
  [[ "$SYNC_KL" == "1" ]] && rsync_kometa_logs "$dry"
  echo "Done."
}

cmd_paths() {
  echo "COSTUME_ROOT=$COSTUME_ROOT"
  echo "KOMETA_CONFIG_SRC=$KOMETA_CONFIG_SRC  → remote $KOMETA_CONFIG_DEST (YAML only in sync -k)"
  echo "KOMETA_ASSETS_SRC=$KOMETA_ASSETS_SRC  → remote $KOMETA_ASSETS_DEST (sync -a; skipped if missing)"
  echo "KOMETA_OVERLAYS_SRC=$KOMETA_OVERLAYS_SRC  → remote $KOMETA_OVERLAYS_DEST (sync -o; skipped if missing)"
  echo "TAUTULLI_SCRIPTS_SRC=$TAUTULLI_SCRIPTS_SRC  → remote $TAUTULLI_SCRIPTS_DEST (sync -t)"
  echo "RADARR_SCRIPTS_SRC=$RADARR_SCRIPTS_SRC  → remote $RADARR_SCRIPTS_DEST (sync -r)"
}

cmd_check() {
  [[ -d "$KOMETA_CONFIG_SRC" ]] || die "Missing directory: $KOMETA_CONFIG_SRC"
  if python3 -c "import yaml" 2>/dev/null; then
    python3 - "$KOMETA_CONFIG_SRC" <<'PY'
import sys
from pathlib import Path
import yaml
root = Path(sys.argv[1])
errs = 0
paths = list(root.rglob("*.yml")) + list(root.rglob("*.yaml"))
for p in sorted(paths):
    try:
        yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"FAIL {p}: {e}", file=sys.stderr)
        errs += 1
if errs:
    sys.exit(1)
print(f"OK: validated YAML under {root} ({len(paths)} files)")
PY
    return
  fi
  if command -v ruby >/dev/null 2>&1; then
    ruby - "$KOMETA_CONFIG_SRC" <<'RUBY' || die "YAML parse failed"
require "yaml"
root = ARGV[0]
paths = Dir.glob(File.join(root, "**", "*.{yml,yaml}"))
errs = 0
paths.sort.each do |p|
  begin
    YAML.load_file(p)
  rescue StandardError => e
    warn "FAIL #{p}: #{e}"
    errs += 1
  end
end
abort if errs.positive?
puts "OK: validated YAML under #{root} (#{paths.size} files)"
RUBY
    return
  fi
  die "Install PyYAML (pip install pyyaml) or use Ruby with YAML for 'check'"
}

cmd_ansible() {
  local ap="${ORTFLIX_ANSIBLE:-$COSTUME_ROOT/../ortflix/k3s/ansible}"
  [[ -f "$ap/deploy.yml" ]] || die "Ansible playbook not found: $ap/deploy.yml (set ORTFLIX_ANSIBLE)"
  local inv="${ANSIBLE_INVENTORY:-$ap/inventory.yml}"
  [[ -f "$inv" ]] || die "Inventory not found: $inv (set ANSIBLE_INVENTORY or create from inventory.example.yml)"
  local -a cmd=(ansible-playbook -i "$inv" "$ap/deploy.yml" --tags kometa-sync,tautulli-sync)
  cmd+=(-e costume_repo_source=local)
  cmd+=(-e "costume_repo_path=$COSTUME_ROOT")
  [[ -n "${ANSIBLE_SECRETS_FILE:-}" ]] && cmd+=(-e "@$ANSIBLE_SECRETS_FILE")
  [[ -n "${ANSIBLE_VAULT_PASS_FILE:-}" ]] && cmd+=(--vault-password-file "$ANSIBLE_VAULT_PASS_FILE")
  echo "Running: ${cmd[*]}"
  "${cmd[@]}"
}

main() {
  local sub="${1:-}"
  shift || true
  case "$sub" in
    check) cmd_check ;;
    paths) cmd_paths ;;
    sync|rsync) cmd_sync 0 "$@" ;;
    sync-dry|dry-run) cmd_sync 1 "$@" ;;
    ansible) cmd_ansible ;;
    ""|-h|--help|help) usage ;;
    *) die "Unknown command: $sub (try: sync, sync-dry, check, paths, ansible)" ;;
  esac
}

main "$@"
