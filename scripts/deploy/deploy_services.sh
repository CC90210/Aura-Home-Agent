#!/usr/bin/env bash
# =============================================================================
# AURA by OASIS — deploy_services.sh
# Deploys Python services (voice-agent, clap-trigger, learning) to the Pi.
#
# This script complements update_configs.sh (which deploys HA YAML configs).
# It copies the Python source code, requirements files, and systemd service
# files to /config/aura/ on the Raspberry Pi, then optionally restarts the
# affected systemd services.
#
# What gets deployed:
#   - voice-agent/     → /config/aura/voice-agent/
#   - clap-trigger/    → /config/aura/clap-trigger/
#   - learning/        → /config/aura/learning/
#   - .env             → /config/aura/.env (if present and --env flag used)
#
# Usage:
#   bash scripts/deploy/deploy_services.sh                    # deploy all
#   bash scripts/deploy/deploy_services.sh --restart          # deploy + restart
#   bash scripts/deploy/deploy_services.sh --service voice    # voice-agent only
#   bash scripts/deploy/deploy_services.sh --service clap     # clap-trigger only
#   bash scripts/deploy/deploy_services.sh --service learning # learning only
#   bash scripts/deploy/deploy_services.sh --env              # also deploy .env
#   bash scripts/deploy/deploy_services.sh --pip              # also pip install
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
RESTART_SERVICES=false
DEPLOY_ENV=false
RUN_PIP=false
SERVICE_FILTER=""  # empty = deploy all

while [[ $# -gt 0 ]]; do
  case "$1" in
    --restart)
      RESTART_SERVICES=true
      shift
      ;;
    --env)
      DEPLOY_ENV=true
      shift
      ;;
    --pip)
      RUN_PIP=true
      shift
      ;;
    --service)
      SERVICE_FILTER="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1"
      echo "Usage: $0 [--restart] [--env] [--pip] [--service voice|clap|learning]"
      exit 1
      ;;
  esac
done

# -----------------------------------------------------------------------------
# Load .env for PI_HOST / PI_USER
# -----------------------------------------------------------------------------
if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: .env file not found at ${ENV_FILE}"
  echo "       Copy .env.example to .env and fill in PI_HOST."
  exit 1
fi

set -o allexport
# shellcheck source=/dev/null
source "${ENV_FILE}"
set +o allexport

PI_HOST="${PI_HOST:-homeassistant.local}"
PI_USER="${PI_USER:-root}"
REMOTE_AURA_DIR="/config/aura"

echo ""
echo "=============================================="
echo "  AURA by OASIS — Deploy Services"
echo "=============================================="
echo "  Target  : ${PI_USER}@${PI_HOST}"
echo "  Remote  : ${REMOTE_AURA_DIR}"
echo "  Filter  : ${SERVICE_FILTER:-all}"
echo "  Restart : ${RESTART_SERVICES}"
echo "  Pip     : ${RUN_PIP}"
echo "  .env    : ${DEPLOY_ENV}"
echo "=============================================="
echo ""

# -----------------------------------------------------------------------------
# Step 1 — Test SSH connectivity
# -----------------------------------------------------------------------------
echo "[1/5] Testing SSH connection to ${PI_HOST}..."
if ! ssh -o ConnectTimeout=10 -o BatchMode=yes \
    "${PI_USER}@${PI_HOST}" "echo 'SSH OK'" &>/dev/null; then
  echo "ERROR: Cannot SSH to ${PI_USER}@${PI_HOST}"
  echo "       Ensure SSH keys are set up and PI_HOST is correct."
  exit 1
fi
echo "      SSH connection OK."
echo ""

# -----------------------------------------------------------------------------
# Step 2 — Ensure remote directories exist
# -----------------------------------------------------------------------------
echo "[2/5] Creating remote directories..."
ssh "${PI_USER}@${PI_HOST}" "
  mkdir -p ${REMOTE_AURA_DIR}/voice-agent
  mkdir -p ${REMOTE_AURA_DIR}/clap-trigger
  mkdir -p ${REMOTE_AURA_DIR}/learning
  mkdir -p ${REMOTE_AURA_DIR}/data
"
echo "      Remote directories ready."
echo ""

# -----------------------------------------------------------------------------
# Step 3 — Deploy Python source files
# -----------------------------------------------------------------------------
echo "[3/5] Deploying Python services..."

deploy_service() {
  local name="$1"
  local local_dir="$2"
  local remote_dir="$3"

  if [[ ! -d "${local_dir}" ]]; then
    echo "      WARN: ${name} directory not found at ${local_dir} — skipping"
    return
  fi

  # Count files to deploy (only .py, .yaml, .txt, .service files)
  local file_count
  file_count=$(find "${local_dir}" -maxdepth 1 \
    \( -name "*.py" -o -name "*.yaml" -o -name "*.txt" -o -name "*.service" \) \
    -type f | wc -l | tr -d ' ')

  # SCP individual files (not subdirectories or __pycache__)
  find "${local_dir}" -maxdepth 1 \
    \( -name "*.py" -o -name "*.yaml" -o -name "*.txt" -o -name "*.service" \) \
    -type f -exec scp -q {} "${PI_USER}@${PI_HOST}:${remote_dir}/" \;

  echo "      ${name} — ${file_count} file(s) deployed to ${remote_dir}"
}

if [[ -z "${SERVICE_FILTER}" || "${SERVICE_FILTER}" == "voice" ]]; then
  deploy_service "voice-agent" "${REPO_ROOT}/voice-agent" "${REMOTE_AURA_DIR}/voice-agent"
fi

if [[ -z "${SERVICE_FILTER}" || "${SERVICE_FILTER}" == "clap" ]]; then
  deploy_service "clap-trigger" "${REPO_ROOT}/clap-trigger" "${REMOTE_AURA_DIR}/clap-trigger"
fi

if [[ -z "${SERVICE_FILTER}" || "${SERVICE_FILTER}" == "learning" ]]; then
  deploy_service "learning" "${REPO_ROOT}/learning" "${REMOTE_AURA_DIR}/learning"
fi

echo ""

# -----------------------------------------------------------------------------
# Step 4 — Deploy .env and install pip dependencies (optional)
# -----------------------------------------------------------------------------
echo "[4/5] Optional deployments..."

if [[ "${DEPLOY_ENV}" == "true" ]]; then
  if [[ -f "${ENV_FILE}" ]]; then
    scp -q "${ENV_FILE}" "${PI_USER}@${PI_HOST}:${REMOTE_AURA_DIR}/.env"
    # Set restrictive permissions on the remote .env
    ssh "${PI_USER}@${PI_HOST}" "chmod 600 ${REMOTE_AURA_DIR}/.env"
    echo "      .env deployed to ${REMOTE_AURA_DIR}/.env (chmod 600)"
  else
    echo "      WARN: .env not found locally — skipping"
  fi
else
  echo "      .env skipped (pass --env to deploy)"
fi

if [[ "${RUN_PIP}" == "true" ]]; then
  echo "      Installing pip dependencies on Pi (this may take a while)..."
  ssh "${PI_USER}@${PI_HOST}" "
    VENV=${REMOTE_AURA_DIR}/.venv
    if [ -x \${VENV}/bin/pip ]; then
      \${VENV}/bin/pip install --quiet -r ${REMOTE_AURA_DIR}/clap-trigger/requirements.txt 2>&1 | tail -1
      if [ -f ${REMOTE_AURA_DIR}/voice-agent/requirements.txt ]; then
        \${VENV}/bin/pip install --quiet -r ${REMOTE_AURA_DIR}/voice-agent/requirements.txt 2>&1 | tail -1
      fi
      echo '      Pip install complete.'
    else
      echo '      WARN: venv not found at \${VENV} — run pi_setup.sh first'
    fi
  "
else
  echo "      pip install skipped (pass --pip to install dependencies)"
fi

echo ""

# -----------------------------------------------------------------------------
# Step 5 — Restart services (optional)
# -----------------------------------------------------------------------------
if [[ "${RESTART_SERVICES}" == "true" ]]; then
  echo "[5/5] Restarting services..."

  ssh "${PI_USER}@${PI_HOST}" "
    if command -v systemctl &>/dev/null; then
      # Reload daemon to pick up any service file changes
      systemctl daemon-reload

      if [[ -z '${SERVICE_FILTER}' || '${SERVICE_FILTER}' == 'clap' ]]; then
        if systemctl is-enabled clap_service &>/dev/null; then
          systemctl restart clap_service
          echo '      clap_service restarted'
        else
          echo '      clap_service not enabled — skipping restart'
        fi
      fi

      if [[ -z '${SERVICE_FILTER}' || '${SERVICE_FILTER}' == 'voice' ]]; then
        if systemctl is-enabled aura_voice &>/dev/null; then
          systemctl restart aura_voice
          echo '      aura_voice restarted'
        else
          echo '      aura_voice not enabled — skipping restart'
        fi
      fi
    else
      echo '      WARN: systemctl not available — cannot restart services'
      echo '      Disable Protection Mode on the SSH add-on to enable systemd access'
    fi
  "
else
  echo "[5/5] Skipping restart (pass --restart to restart services automatically)."
fi

echo ""
echo "=============================================="
echo "  Service deployment complete!"
echo "=============================================="
echo ""
echo "Quick commands (run on Pi via SSH):"
echo "  journalctl -u clap_service -f     # Watch clap detector logs"
echo "  journalctl -u aura_voice -f       # Watch voice agent logs"
echo "  systemctl status clap_service     # Check clap detector status"
echo "  systemctl status aura_voice       # Check voice agent status"
echo ""
