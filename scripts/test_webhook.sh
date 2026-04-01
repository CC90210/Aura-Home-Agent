#!/usr/bin/env bash
# =============================================================================
# AURA by OASIS — test_webhook.sh
# Fires a test POST to a Home Assistant webhook endpoint.
#
# Useful for:
#   - Verifying an automation fires correctly without clapping
#   - Testing a scene trigger during setup
#   - Debugging webhook-based automations
#
# Webhook IDs map to clap patterns defined in home-assistant/automations/:
#   double_clap   → aura_double_clap  (Welcome Home toggle)
#   triple_clap   → aura_triple_clap  (Studio mode)
#   quad_clap     → aura_quad_clap    (Party mode)
#   goodnight     → aura_goodnight
#   morning       → aura_morning
#
# Usage:
#   bash scripts/test_webhook.sh <webhook_name>
#
# Examples:
#   bash scripts/test_webhook.sh double_clap
#   bash scripts/test_webhook.sh goodnight
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Resolve repo root and load .env
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: .env file not found at ${ENV_FILE}"
  echo "       Copy .env.example to .env and set HA_URL."
  exit 1
fi

set -o allexport
# shellcheck source=/dev/null
source "${ENV_FILE}"
set +o allexport

# -----------------------------------------------------------------------------
# Parse argument
# -----------------------------------------------------------------------------
if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <webhook_name>"
  echo ""
  echo "Known webhook names:"
  echo "  double_clap   — Toggle Welcome Home scene"
  echo "  triple_clap   — Toggle Studio / Content mode"
  echo "  quad_clap     — Toggle Party mode"
  echo "  goodnight     — Goodnight routine"
  echo "  morning       — Morning routine"
  echo "  movie_mode    — Movie mode"
  echo "  focus_mode    — Focus / Deep Work mode"
  echo ""
  echo "Example:"
  echo "  $0 double_clap"
  exit 1
fi

WEBHOOK_NAME="$1"

# Prefix with "aura_" if the caller didn't include it, for convenience
if [[ "${WEBHOOK_NAME}" != aura_* ]]; then
  WEBHOOK_ID="aura_${WEBHOOK_NAME}"
else
  WEBHOOK_ID="${WEBHOOK_NAME}"
fi

HA_URL="${HA_URL:-http://homeassistant.local:8123}"
ENDPOINT="${HA_URL}/api/webhook/${WEBHOOK_ID}"

echo ""
echo "=============================================="
echo "  AURA by OASIS — Webhook Tester"
echo "=============================================="
echo "  Webhook ID : ${WEBHOOK_ID}"
echo "  Endpoint   : ${ENDPOINT}"
echo "=============================================="
echo ""
echo "Firing webhook..."
echo ""

# Send the POST request and capture both the HTTP status code and the response body
HTTP_RESPONSE=$(curl \
  --silent \
  --include \
  --max-time 15 \
  --write-out "\n---HTTP_STATUS:%{http_code}" \
  -X POST "${ENDPOINT}" \
  -H "Content-Type: application/json" \
  -d '{"source": "aura_test_webhook"}' \
  2>&1)

# Split response body from status code line
HTTP_STATUS=$(echo "${HTTP_RESPONSE}" | grep "^---HTTP_STATUS:" | cut -d: -f2)
RESPONSE_BODY=$(echo "${HTTP_RESPONSE}" | grep -v "^---HTTP_STATUS:")

echo "Response:"
echo "${RESPONSE_BODY}"
echo ""

# Interpret result
case "${HTTP_STATUS}" in
  200)
    echo "Result: SUCCESS (HTTP 200) — automation triggered."
    ;;
  "")
    echo "Result: FAILED — no response received."
    echo "        Is Home Assistant running at ${HA_URL}?"
    exit 1
    ;;
  *)
    echo "Result: HTTP ${HTTP_STATUS}"
    if [[ "${HTTP_STATUS}" == "404" ]]; then
      echo "        Webhook '${WEBHOOK_ID}' not found in Home Assistant."
      echo "        Check the webhook_id in the automation YAML matches exactly."
    elif [[ "${HTTP_STATUS}" == "401" ]]; then
      echo "        Unauthorized — webhooks should not require auth."
      echo "        Make sure 'local_only: true' is set in the automation."
    fi
    exit 1
    ;;
esac

echo ""
