#!/usr/bin/env bash
# =============================================================================
# AURA by OASIS — update_configs.sh
# Deploys Home Assistant YAML configs from this repo to the Raspberry Pi.
#
# The script:
#   1. Reads PI_HOST and PI_USER from .env (falls back to sensible defaults)
#   2. Creates a timestamped backup of the existing /config/ directory on the Pi
#   3. SCPs the home-assistant/ tree to /config/ on the Pi
#   4. Optionally restarts Home Assistant (pass --restart flag)
#
# Usage:
#   bash scripts/deploy/update_configs.sh             # deploy only
#   bash scripts/deploy/update_configs.sh --restart   # deploy + restart HA
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Resolve repo root
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"

# -----------------------------------------------------------------------------
# Parse flags
# -----------------------------------------------------------------------------
RESTART_HA=false
for arg in "$@"; do
  case "${arg}" in
    --restart)
      RESTART_HA=true
      ;;
    *)
      echo "Unknown argument: ${arg}"
      echo "Usage: $0 [--restart]"
      exit 1
      ;;
  esac
done

# -----------------------------------------------------------------------------
# Load .env
# -----------------------------------------------------------------------------
if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: .env file not found at ${ENV_FILE}"
  echo "       Copy .env.example to .env and fill in your values."
  exit 1
fi

set -o allexport
# shellcheck source=/dev/null
source "${ENV_FILE}"
set +o allexport

# Apply defaults if variables are not set in .env
PI_HOST="${PI_HOST:-homeassistant.local}"
PI_USER="${PI_USER:-root}"

# Remote paths
REMOTE_CONFIG_DIR="/config"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
REMOTE_BACKUP_DIR="/config_backups/backup_${TIMESTAMP}"

# Local source directory
LOCAL_HA_DIR="${REPO_ROOT}/home-assistant"

echo ""
echo "=============================================="
echo "  AURA by OASIS — Deploy Configs"
echo "=============================================="
echo "  Target  : ${PI_USER}@${PI_HOST}"
echo "  Source  : ${LOCAL_HA_DIR}"
echo "  Dest    : ${REMOTE_CONFIG_DIR}"
echo "  Backup  : ${REMOTE_BACKUP_DIR}"
echo "  Restart : ${RESTART_HA}"
echo "=============================================="
echo ""

# -----------------------------------------------------------------------------
# Verify local source exists
# -----------------------------------------------------------------------------
if [[ ! -d "${LOCAL_HA_DIR}" ]]; then
  echo "ERROR: home-assistant/ directory not found at ${LOCAL_HA_DIR}"
  exit 1
fi

# -----------------------------------------------------------------------------
# Step 1 — Test SSH connectivity before doing anything destructive
# -----------------------------------------------------------------------------
echo "[1/4] Testing SSH connection to ${PI_HOST}..."
if ! ssh -o ConnectTimeout=10 -o BatchMode=yes \
    "${PI_USER}@${PI_HOST}" "echo 'SSH OK'" &>/dev/null; then
  echo "ERROR: Cannot connect to ${PI_USER}@${PI_HOST} via SSH."
  echo "       Make sure:"
  echo "         - The Pi is on and connected to the network"
  echo "         - SSH keys are set up (ssh-copy-id ${PI_USER}@${PI_HOST})"
  echo "         - PI_HOST and PI_USER in .env are correct"
  exit 1
fi
echo "      SSH connection OK."
echo ""

# -----------------------------------------------------------------------------
# Step 2 — Back up existing configs on the Pi
# -----------------------------------------------------------------------------
echo "[2/4] Backing up existing /config on Pi..."
ssh "${PI_USER}@${PI_HOST}" "
  mkdir -p /config_backups
  if [ -d ${REMOTE_CONFIG_DIR} ]; then
    cp -r ${REMOTE_CONFIG_DIR} ${REMOTE_BACKUP_DIR}
    echo '      Backup created at ${REMOTE_BACKUP_DIR}'
  else
    echo '      No existing /config to back up — skipping.'
  fi
"
echo ""

# -----------------------------------------------------------------------------
# Step 3 — SCP configs to the Pi
# We use scp -r to copy the entire home-assistant/ tree.
# Each subdirectory (automations/, scenes/, etc.) is deployed individually so
# we get clear output of what was transferred.
# -----------------------------------------------------------------------------
echo "[3/4] Deploying configs..."

SUBDIRS=("automations" "scenes" "scripts" "dashboards" "packages")
DEPLOYED=()

for subdir in "${SUBDIRS[@]}"; do
  local_path="${LOCAL_HA_DIR}/${subdir}"
  if [[ -d "${local_path}" ]]; then
    # Ensure the destination directory exists on the Pi
    ssh "${PI_USER}@${PI_HOST}" "mkdir -p ${REMOTE_CONFIG_DIR}/${subdir}"
    scp -q -r "${local_path}/." "${PI_USER}@${PI_HOST}:${REMOTE_CONFIG_DIR}/${subdir}/"
    FILE_COUNT=$(find "${local_path}" -type f | wc -l | tr -d ' ')
    echo "      ${subdir}/ — ${FILE_COUNT} file(s) deployed"
    DEPLOYED+=("${subdir}")
  else
    echo "      ${subdir}/ — skipped (directory not present locally)"
  fi
done

echo ""
echo "      Deployed directories: ${DEPLOYED[*]}"
echo ""

# -----------------------------------------------------------------------------
# Step 4 — Optionally restart Home Assistant
# -----------------------------------------------------------------------------
if [[ "${RESTART_HA}" == "true" ]]; then
  echo "[4/4] Restarting Home Assistant..."
  ssh "${PI_USER}@${PI_HOST}" "ha core restart" || {
    echo "      'ha core restart' failed — trying the REST API instead..."
    HA_URL="${HA_URL:-http://homeassistant.local:8123}"
    HA_TOKEN="${HA_TOKEN:-}"
    if [[ -n "${HA_TOKEN}" ]]; then
      curl --silent --output /dev/null \
        -X POST "${HA_URL}/api/services/homeassistant/restart" \
        -H "Authorization: Bearer ${HA_TOKEN}" \
        -H "Content-Type: application/json"
      echo "      Restart triggered via REST API."
    else
      echo "      HA_TOKEN not set — cannot trigger restart via API."
      echo "      Restart Home Assistant manually: Settings → System → Restart"
    fi
  }
  echo "      Home Assistant restart triggered. Allow 30-60 seconds for it to come back up."
else
  echo "[4/4] Skipping restart (run with --restart to restart Home Assistant automatically)."
fi

echo ""
echo "=============================================="
echo "  Deploy complete!"
echo "=============================================="
echo ""
echo "If Home Assistant didn't restart, reload automations in the UI:"
echo "  Settings → Automations & Scenes → (top-right menu) → Reload automations"
echo ""
echo "To restore the previous config from backup:"
echo "  ssh ${PI_USER}@${PI_HOST}"
echo "  cp -r ${REMOTE_BACKUP_DIR}/. ${REMOTE_CONFIG_DIR}/"
echo "  ha core restart"
echo ""
