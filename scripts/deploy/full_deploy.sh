#!/usr/bin/env bash
# =============================================================================
# AURA by OASIS — full_deploy.sh
# One-command full deployment: YAML configs + Python services + optional restart.
#
# This orchestrates update_configs.sh and deploy_services.sh so you can ship
# everything to the Pi with a single command.
#
# Usage:
#   bash scripts/deploy/full_deploy.sh                  # deploy everything
#   bash scripts/deploy/full_deploy.sh --restart         # deploy + restart HA + services
#   bash scripts/deploy/full_deploy.sh --env             # also deploy .env
#   bash scripts/deploy/full_deploy.sh --pip             # also install pip deps
#   bash scripts/deploy/full_deploy.sh --restart --env   # the full monty
#
# What happens:
#   1. Validates .env and SSH connectivity
#   2. Deploys HA YAML configs (update_configs.sh)
#   3. Deploys Python services (deploy_services.sh)
#   4. Optionally restarts HA and systemd services
#   5. Runs a quick health check
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"

# Parse flags — pass through to sub-scripts
RESTART_FLAG=""
ENV_FLAG=""
PIP_FLAG=""
EXTRA_ARGS=()

for arg in "$@"; do
  case "${arg}" in
    --restart) RESTART_FLAG="--restart" ;;
    --env)     ENV_FLAG="--env" ;;
    --pip)     PIP_FLAG="--pip" ;;
    *)
      echo "Unknown argument: ${arg}"
      echo "Usage: $0 [--restart] [--env] [--pip]"
      exit 1
      ;;
  esac
done

# Load .env
if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: .env not found at ${ENV_FILE}"
  exit 1
fi

set -o allexport
source "${ENV_FILE}"
set +o allexport

PI_HOST="${PI_HOST:-homeassistant.local}"

echo ""
echo "================================================================"
echo "  AURA by OASIS — Full Deployment"
echo "  Target: ${PI_HOST}"
echo "  Time  : $(date '+%Y-%m-%d %H:%M:%S')"
echo "================================================================"
echo ""

# -------------------------------------------------------------------------
# Phase 1 — Validate YAML locally before deploying
# -------------------------------------------------------------------------
echo "--- Phase 1: YAML Validation ---"
echo ""

YAML_ERRORS=0
if command -v python3 &>/dev/null; then
  python3 -c "
import yaml, glob, sys
errors = 0
files = glob.glob('${REPO_ROOT}/home-assistant/**/*.yaml', recursive=True)
for f in files:
    try:
        with open(f) as fh:
            yaml.safe_load(fh)
    except Exception as e:
        print(f'  YAML ERROR: {f}: {e}')
        errors += 1
if errors:
    print(f'  {errors} YAML file(s) have errors.')
    sys.exit(1)
else:
    print(f'  All {len(files)} YAML files are valid.')
" || YAML_ERRORS=1

  if [[ "${YAML_ERRORS}" -eq 1 ]]; then
    echo ""
    echo "ERROR: Fix YAML errors before deploying."
    exit 1
  fi
else
  echo "  python3 not available — skipping YAML validation"
fi
echo ""

# -------------------------------------------------------------------------
# Phase 2 — Deploy HA configs
# -------------------------------------------------------------------------
echo "--- Phase 2: Deploy Home Assistant Configs ---"
echo ""
bash "${SCRIPT_DIR}/update_configs.sh" ${RESTART_FLAG}
echo ""

# -------------------------------------------------------------------------
# Phase 3 — Deploy Python services
# -------------------------------------------------------------------------
echo "--- Phase 3: Deploy Python Services ---"
echo ""
bash "${SCRIPT_DIR}/deploy_services.sh" ${RESTART_FLAG} ${ENV_FLAG} ${PIP_FLAG}
echo ""

# -------------------------------------------------------------------------
# Phase 4 — Quick health check
# -------------------------------------------------------------------------
echo "--- Phase 4: Health Check ---"
echo ""

HA_URL="${HA_URL:-http://homeassistant.local:8123}"
HTTP_STATUS=$(curl --silent --output /dev/null --write-out "%{http_code}" \
  --max-time 15 "${HA_URL}/api/" 2>/dev/null || echo "000")

if [[ "${HTTP_STATUS}" == "200" || "${HTTP_STATUS}" == "401" ]]; then
  echo "  Home Assistant is reachable (HTTP ${HTTP_STATUS})"
else
  echo "  WARNING: Home Assistant returned HTTP ${HTTP_STATUS}"
  echo "  It may still be restarting — check again in 30-60 seconds."
fi

# Check services if we can SSH in
ssh -o ConnectTimeout=5 -o BatchMode=yes "${PI_USER:-root}@${PI_HOST}" "
  if command -v systemctl &>/dev/null; then
    for svc in clap_service aura_voice; do
      if systemctl is-enabled \${svc} &>/dev/null; then
        STATUS=\$(systemctl is-active \${svc} 2>/dev/null || echo 'unknown')
        echo \"  \${svc}: \${STATUS}\"
      fi
    done
  fi
" 2>/dev/null || echo "  Could not SSH to check service status."

echo ""
echo "================================================================"
echo "  Full deployment complete!"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "================================================================"
echo ""
