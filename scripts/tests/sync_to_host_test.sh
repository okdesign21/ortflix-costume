#!/usr/bin/env bash
# Exercise sync command construction offline; never contact a server.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYNC_SCRIPT="$SCRIPT_DIR/../sync_to_host.sh"
TEST_ROOT="$(mktemp -d)"
trap 'rm -rf -- "$TEST_ROOT"' EXIT

mkdir -p "$TEST_ROOT/bin" "$TEST_ROOT/config/assets" "$TEST_ROOT/config/overlays"
export SSH_LOG="$TEST_ROOT/ssh.log"
export RSYNC_LOG="$TEST_ROOT/rsync.log"
export MUTATION_LOG="$TEST_ROOT/mutations.log"
export SYNC_ENV_FILE="$TEST_ROOT/missing.env"
export ORTFLIX_SYNC_HOST="example.invalid"
export ORTFLIX_SYNC_USER="sync-test"
export ORTFLIX_SYNC_PORT="2222"
export KOMETA_CONFIG_SRC="$TEST_ROOT/config"
export KOMETA_ASSETS_SRC="$TEST_ROOT/config/assets"
export KOMETA_OVERLAYS_SRC="$TEST_ROOT/config/overlays"
export KOMETA_CONFIG_DEST="/remote/config"
export KOMETA_ASSETS_DEST="/remote/config/assets"
export KOMETA_OVERLAYS_DEST="/remote/config/overlays"
export ORTFLIX_RSYNC_DELETE=1

cat > "$TEST_ROOT/bin/ssh" <<'SH'
#!/usr/bin/env bash
printf '%q ' "$@" >> "$SSH_LOG"
printf '\n' >> "$SSH_LOG"
printf 'ssh\n' >> "$MUTATION_LOG"
SH

cat > "$TEST_ROOT/bin/rsync" <<'SH'
#!/usr/bin/env bash
printf '%q ' "$@" >> "$RSYNC_LOG"
printf '\n' >> "$RSYNC_LOG"
for arg in "$@"; do
  [[ "$arg" == "--dry-run" ]] && exit 0
done
printf 'rsync\n' >> "$MUTATION_LOG"
SH

chmod +x "$TEST_ROOT/bin/ssh" "$TEST_ROOT/bin/rsync"
export PATH="$TEST_ROOT/bin:$PATH"
cd "$TEST_ROOT"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

reset_logs() {
  : > "$SSH_LOG"
  : > "$RSYNC_LOG"
  : > "$MUTATION_LOG"
}

for command in sync-dry dry-run; do
  for selector in default -k -a -o -kl combined; do
    reset_logs
    flags=()
    expected=1
    case "$selector" in
      default) expected=3 ;;
      -kl) flags=(-kl); expected=2 ;;
      combined) flags=(-k -a -o -kl); expected=5 ;;
      *) flags=("$selector") ;;
    esac
    bash "$SYNC_SCRIPT" "$command" "${flags[@]}"
    [[ ! -s "$SSH_LOG" ]] || fail "$command $selector invoked remote setup"
    [[ ! -s "$MUTATION_LOG" ]] || fail "$command $selector requested mutations"
    [[ "$(wc -l < "$RSYNC_LOG")" -eq "$expected" ]] ||
      fail "$command $selector did not preview all selected transfers"
    [[ "$(grep -c -- '--dry-run' "$RSYNC_LOG")" -eq "$expected" ]] ||
      fail "$command $selector omitted --dry-run"
    if [[ "$selector" != "-kl" ]]; then
      grep -q -- '--delete' "$RSYNC_LOG" || fail "delete preview was lost"
    fi
  done
done

for command in sync rsync; do
  reset_logs
  bash "$SYNC_SCRIPT" "$command" -k -a -o
  [[ "$(wc -l < "$SSH_LOG")" -eq 1 ]] || fail "$command skipped remote setup"
  grep -q -- 'mkdir' "$SSH_LOG" || fail "$command omitted directory creation"
  [[ "$(wc -l < "$RSYNC_LOG")" -eq 3 ]] || fail "$command skipped transfers"
  [[ "$(wc -l < "$MUTATION_LOG")" -eq 4 ]] || fail "$command unexpectedly dry-ran"
done

echo "OK: sync previews are non-mutating; normal sync retains remote setup"
