#!/bin/bash

# Script to generate .env file from docker_secrets/
# Maps secret files to KOMETA env variables
#
# Usage:
#   ./generate_kometa_env.sh          # Uses SERVER_IP from .env (docker-compose)
#   ./generate_kometa_env.sh -k3      # Uses K3s service DNS names (k3s mode)

# Determine script directory and repo root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

SECRETS_DIR="${REPO_ROOT}/docker_secrets"
ENV_FILE="${REPO_ROOT}/kometa/config/.env"
K3S_MODE=0

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -k3)
            K3S_MODE=1
            shift
            ;;
        *)
            echo "Unknown flag: $1"
            exit 1
            ;;
    esac
done

# Load SERVER_IP from repo root .env when present (falls back to current environment)
if [ -f "${REPO_ROOT}/.env" ]; then
    # shellcheck source=/dev/null
    . "${REPO_ROOT}/.env"
fi

# Create kometa/config directory if it doesn't exist
mkdir -p "${REPO_ROOT}/kometa/config"

# Create or overwrite the .env file
true > "$ENV_FILE"

# Helper to append a line if the secret file exists
add_secret() {
    local secret_file="$1"
    local env_name_raw="$2"
    local default_value="${3:-}"

    # Change env for Kometa format (remove underscores and add KOMETA_ prefix)
    local env_name="${env_name_raw//_/}"
    env_name="KOMETA_$(echo "$env_name" | tr '[:lower:]' '[:upper:]')"

    if [ -f "$SECRETS_DIR/$secret_file" ]; then
        VALUE=$(cat "$SECRETS_DIR/$secret_file" | tr -d '\r\n')
        echo "${env_name}=${VALUE}" >> "$ENV_FILE"
        echo "✓ Added ${env_name} from ${secret_file}"
    elif [ -n "$default_value" ]; then
        echo "${env_name}=${default_value}" >> "$ENV_FILE"
        echo "✓ Added ${env_name} default value"
    fi
}

add_secret "plex_token" "plex_token"
add_secret "tmdb_api_key" "tmdb_api_key"
add_secret "tautulli_api_key" "tautulli_api_key"

# Default URLs based on environment (K3s or docker-compose)
if [ "$K3S_MODE" -eq 1 ]; then
    # K3s service DNS: service_name.namespace.svc.cluster.local (short form: service.namespace)
    add_secret "tautulli_url" "tautulli_url" "http://tautulli.ortflix-media:8181"
    add_secret "plex_url" "plex_url" "http://plex.ortflix-infra:32400"
    echo ""
    echo "✓ K3s mode (-k3): Using service DNS"
else
    # Docker-compose: use SERVER_IP from .env and standard ports
    add_secret "tautulli_url" "tautulli_url" "http://${SERVER_IP}:8181"
    add_secret "plex_url" "plex_url" "http://${SERVER_IP}:32400"
fi

echo ""
echo ".env file created at: $ENV_FILE"
