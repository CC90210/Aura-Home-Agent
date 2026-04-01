#!/usr/bin/env bash
# =============================================================================
# AURA by OASIS — deploy_client.sh
# Deploys AURA to a specific client's Raspberry Pi.
#
# How it works:
#   1. Validates the client name and checks clients/{client_name}/ exists
#   2. Loads the client-specific .env file (clients/{client_name}/.env)
#   3. Merges base configs (home-assistant/) with client overrides
#      (clients/{client_name}/home-assistant/) into a temp directory
#   4. Deploys the merged configs to the client's Pi via SCP
#   5. Optionally restarts Home Assistant (--restart flag)
#
# Client overrides take precedence: a file in clients/{name}/home-assistant/
# automations/foo.yaml will REPLACE the base automations/foo.yaml.
# Files that exist only in the base are included as-is.
# Files that exist only in the client override are also included.
#
# Usage:
#   bash scripts/deploy/deploy_client.sh <client_name>
#   bash scripts/deploy/deploy_client.sh <client_name> --restart
#
# Example:
#   bash scripts/deploy/deploy_client.sh smith_residence
#   bash scripts/deploy/deploy_client.sh smith_residence --restart
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Resolve repo root
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# -----------------------------------------------------------------------------
# Parse arguments
# -----------------------------------------------------------------------------
if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <client_name> [--restart]"
  echo ""
  echo "Available clients:"
  if [[ -d "${REPO_ROOT}/clients" ]]; then
    find "${REPO_ROOT}/clients" -mindepth 1 -maxdepth 1 -type d \
      ! -name '.template' -printf "  %f\n" 2>/dev/null \
      || ls -1 "${REPO_ROOT}/clients/" | grep -v '.template' | sed 's/^/  /'
  fi
  exit 1
fi

CLIENT_NAME="$1"
RESTART_HA=false

for arg in "${@:2}"; do
  case "${arg}" in
    --restart)
      RESTART_HA=true
      ;;
    *)
      echo "Unknown argument: ${arg}"
      echo "Usage: $0 <client_name> [--restart]"
      exit 1
      ;;
  esac
done

# -----------------------------------------------------------------------------
# Validate client directory exists
# -----------------------------------------------------------------------------
CLIENT_DIR="${REPO_ROOT}/clients/${CLIENT_NAME}"

if [[ ! -d "${CLIENT_DIR}" ]]; then
  echo "ERROR: Client '${CLIENT_NAME}' not found."
  echo "       Expected directory: ${CLIENT_DIR}"
  echo ""
  echo "To create a new client, copy the template:"
  echo "  cp -r ${REPO_ROOT}/clients/.template ${CLIENT_DIR}"
  exit 1
fi

# -----------------------------------------------------------------------------
# Load client-specific .env
# -----------------------------------------------------------------------------
CLIENT_ENV="${CLIENT_DIR}/.env"

if [[ ! -f "${CLIENT_ENV}" ]]; then
  echo "ERROR: Client .env not found at ${CLIENT_ENV}"
  echo "       Copy .env.example to ${CLIENT_ENV} and fill in the client's values."
  exit 1
fi

set -o allexport
# shellcheck source=/dev/null
source "${CLIENT_ENV}"
set +o allexport

# Required variables for deployment
PI_HOST="${PI_HOST:?PI_HOST must be set in ${CLIENT_ENV}}"
PI_USER="${PI_USER:-root}"

REMOTE_CONFIG_DIR="/config"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
REMOTE_BACKUP_DIR="/config_backups/aura_backup_${TIMESTAMP}"

echo ""
echo "=============================================="
echo "  AURA by OASIS — Client Deploy"
echo "=============================================="
echo "  Client  : ${CLIENT_NAME}"
echo "  Target  : ${PI_USER}@${PI_HOST}"
echo "  Dest    : ${REMOTE_CONFIG_DIR}"
echo "  Backup  : ${REMOTE_BACKUP_DIR}"
echo "  Restart : ${RESTART_HA}"
echo "=============================================="
echo ""

# -----------------------------------------------------------------------------
# Step 1 — Test SSH connectivity
# -----------------------------------------------------------------------------
echo "[1/5] Testing SSH connection to ${PI_HOST}..."
if ! ssh -o ConnectTimeout=10 -o BatchMode=yes \
    "${PI_USER}@${PI_HOST}" "echo 'SSH OK'" &>/dev/null; then
  echo "ERROR: Cannot SSH to ${PI_USER}@${PI_HOST}"
  echo "       Check PI_HOST in ${CLIENT_ENV} and ensure SSH keys are set up."
  exit 1
fi
echo "      SSH connection OK."
echo ""

# -----------------------------------------------------------------------------
# Step 2 — Merge base + client override configs into a temp directory
# The merge logic:
#   - Start with a full copy of home-assistant/ (base configs)
#   - Overlay clients/{name}/home-assistant/ on top (overrides win)
# This way any file the client doesn't customise gets the base version.
# -----------------------------------------------------------------------------
echo "[2/5] Merging base configs with client overrides..."

MERGE_DIR=$(mktemp -d)
# Ensure temp dir is cleaned up on exit (success or failure)
trap 'rm -rf "${MERGE_DIR}"' EXIT

BASE_HA_DIR="${REPO_ROOT}/home-assistant"
CLIENT_HA_DIR="${CLIENT_DIR}/home-assistant"

# Copy base configs
if [[ -d "${BASE_HA_DIR}" ]]; then
  cp -r "${BASE_HA_DIR}/." "${MERGE_DIR}/"
  echo "      Base configs copied from ${BASE_HA_DIR}"
else
  echo "WARNING: Base home-assistant/ directory not found at ${BASE_HA_DIR}"
fi

# Apply client overrides (cp -r with overlay — newer files win)
if [[ -d "${CLIENT_HA_DIR}" ]]; then
  cp -r "${CLIENT_HA_DIR}/." "${MERGE_DIR}/"
  OVERRIDE_COUNT=$(find "${CLIENT_HA_DIR}" -type f | wc -l | tr -d ' ')
  echo "      Client overrides applied: ${OVERRIDE_COUNT} file(s) from ${CLIENT_HA_DIR}"
else
  echo "      No client-specific overrides (${CLIENT_HA_DIR} does not exist) — using base only."
fi

TOTAL_FILES=$(find "${MERGE_DIR}" -type f | wc -l | tr -d ' ')
echo "      Merged config total: ${TOTAL_FILES} file(s)"
echo ""

# -----------------------------------------------------------------------------
# Step 3 — Back up existing configs on the Pi
# -----------------------------------------------------------------------------
echo "[3/5] Backing up existing /config on client Pi..."
ssh "${PI_USER}@${PI_HOST}" "
  mkdir -p /config_backups
  if [ -d ${REMOTE_CONFIG_DIR} ]; then
    cp -r ${REMOTE_CONFIG_DIR} ${REMOTE_BACKUP_DIR}
    echo '      Backup created at ${REMOTE_BACKUP_DIR}'
  else
    echo '      No existing /config to back up.'
  fi
"
echo ""

# -----------------------------------------------------------------------------
# Step 4 — Deploy merged configs to client Pi
# -----------------------------------------------------------------------------
echo "[4/5] Deploying merged configs..."

SUBDIRS=("automations" "scenes" "scripts" "dashboards" "packages")
DEPLOYED=()

for subdir in "${SUBDIRS[@]}"; do
  local_path="${MERGE_DIR}/${subdir}"
  if [[ -d "${local_path}" ]]; then
    ssh "${PI_USER}@${PI_HOST}" "mkdir -p ${REMOTE_CONFIG_DIR}/${subdir}"
    scp -q -r "${local_path}/." "${PI_USER}@${PI_HOST}:${REMOTE_CONFIG_DIR}/${subdir}/"
    FILE_COUNT=$(find "${local_path}" -type f | wc -l | tr -d ' ')
    echo "      ${subdir}/ — ${FILE_COUNT} file(s) deployed"
    DEPLOYED+=("${subdir}")
  else
    echo "      ${subdir}/ — skipped (not present in merged output)"
  fi
done

# Deploy configuration.yaml (the root HA config)
# This file contains !include directives and input_boolean declarations that
# Home Assistant must read at startup — it cannot be omitted from deployment.
merged_config_yaml="${MERGE_DIR}/configuration.yaml"
if [[ -f "${merged_config_yaml}" ]]; then
  echo "Deploying configuration.yaml..."
  scp -q "${merged_config_yaml}" "${PI_USER}@${PI_HOST}:${REMOTE_CONFIG_DIR}/configuration.yaml"
  echo "      configuration.yaml deployed"
else
  echo "      configuration.yaml — skipped (not present in merged output)"
fi

echo ""

# -----------------------------------------------------------------------------
# Step 5 — Optionally restart Home Assistant
# -----------------------------------------------------------------------------
if [[ "${RESTART_HA}" == "true" ]]; then
  echo "[5/5] Restarting Home Assistant on client Pi..."
  ssh "${PI_USER}@${PI_HOST}" "ha core restart" || {
    echo "      'ha core restart' failed — attempting REST API restart..."
    HA_URL="${HA_URL:-http://${PI_HOST}:8123}"
    HA_TOKEN="${HA_TOKEN:-}"
    if [[ -n "${HA_TOKEN}" ]]; then
      curl --silent --output /dev/null \
        -X POST "${HA_URL}/api/services/homeassistant/restart" \
        -H "Authorization: Bearer ${HA_TOKEN}" \
        -H "Content-Type: application/json"
      echo "      Restart triggered via REST API."
    else
      echo "      HA_TOKEN not set in ${CLIENT_ENV} — cannot restart via API."
    fi
  }
else
  echo "[5/5] Skipping restart (pass --restart to restart Home Assistant automatically)."
fi

echo ""
echo "=============================================="
echo "  Client deployment complete!"
echo "=============================================="
echo ""
echo "  Client    : ${CLIENT_NAME}"
echo "  Deployed  : ${DEPLOYED[*]}"
echo "  Backup at : ${REMOTE_BACKUP_DIR} (on Pi)"
echo ""
echo "To restore backup if something is wrong:"
echo "  ssh ${PI_USER}@${PI_HOST}"
echo "  cp -r ${REMOTE_BACKUP_DIR}/. ${REMOTE_CONFIG_DIR}/"
echo "  ha core restart"
echo ""
