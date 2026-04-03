#!/usr/bin/env bash
# =============================================================================
# AURA by OASIS — Interactive Setup Wizard
# Walks through first-time configuration on a fresh machine.
#
# This wizard:
#   1. Checks prerequisites (Python, Node, SSH keys)
#   2. Generates a .env file from prompts
#   3. Validates the Home Assistant connection
#   4. Optionally generates a dashboard auth token
#   5. Gives a deployment-ready summary
#
# Usage:
#   bash scripts/setup/wizard.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"
ENV_EXAMPLE="${REPO_ROOT}/.env.example"

# Colors
if [[ -t 1 ]]; then
  BOLD="\033[1m"
  CYAN="\033[1;36m"
  GREEN="\033[0;32m"
  YELLOW="\033[0;33m"
  RED="\033[0;31m"
  PURPLE="\033[0;35m"
  RESET="\033[0m"
else
  BOLD="" CYAN="" GREEN="" YELLOW="" RED="" PURPLE="" RESET=""
fi

# =============================================================================
# Banner
# =============================================================================
echo ""
echo -e "${PURPLE}"
echo "    █████╗ ██╗   ██╗██████╗  █████╗ "
echo "   ██╔══██╗██║   ██║██╔══██╗██╔══██╗"
echo "   ███████║██║   ██║██████╔╝███████║"
echo "   ██╔══██║██║   ██║██╔══██╗██╔══██║"
echo "   ██║  ██║╚██████╔╝██║  ██║██║  ██║"
echo "   ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝"
echo -e "${RESET}"
echo -e "${CYAN}   Ambient. Unified. Responsive. Automated.${RESET}"
echo -e "${BOLD}   by OASIS AI Solutions${RESET}"
echo ""
echo "   Welcome to the AURA Setup Wizard."
echo "   This will walk you through first-time configuration."
echo ""

# =============================================================================
# Step 1 — Prerequisites
# =============================================================================
echo -e "${CYAN}━━━ Step 1/5: Prerequisites ━━━${RESET}"
echo ""

MISSING=0

check_tool() {
  local name="$1"
  local cmd="$2"
  if command -v "${cmd}" &>/dev/null; then
    echo -e "  ${GREEN}✓${RESET} ${name} found: $(command -v ${cmd})"
  else
    echo -e "  ${RED}✗${RESET} ${name} not found"
    MISSING=$((MISSING + 1))
  fi
}

check_tool "Python 3" "python3"
check_tool "Node.js" "node"
check_tool "npm" "npm"
check_tool "Git" "git"
check_tool "SSH" "ssh"
check_tool "SCP" "scp"
check_tool "curl" "curl"

echo ""

if [[ "${MISSING}" -gt 0 ]]; then
  echo -e "${YELLOW}Warning: ${MISSING} tool(s) missing.${RESET}"
  echo "  Some features may not work. Install missing tools before deploying."
  echo ""
fi

# =============================================================================
# Step 2 — Generate .env
# =============================================================================
echo -e "${CYAN}━━━ Step 2/5: Environment Configuration ━━━${RESET}"
echo ""

if [[ -f "${ENV_FILE}" ]]; then
  echo -e "  ${GREEN}✓${RESET} .env file already exists at ${ENV_FILE}"
  echo ""
  read -rp "  Overwrite with fresh values? (y/N): " OVERWRITE
  if [[ "${OVERWRITE}" != "y" && "${OVERWRITE}" != "Y" ]]; then
    echo "  Keeping existing .env"
    SKIP_ENV=true
  else
    SKIP_ENV=false
  fi
else
  SKIP_ENV=false
fi

if [[ "${SKIP_ENV}" == "false" ]]; then
  echo ""
  echo "  Fill in your configuration values."
  echo "  Press Enter to accept defaults shown in [brackets]."
  echo ""

  read -rp "  Home Assistant URL [http://homeassistant.local:8123]: " HA_URL
  HA_URL="${HA_URL:-http://homeassistant.local:8123}"

  read -rp "  HA Long-Lived Access Token: " HA_TOKEN
  if [[ -z "${HA_TOKEN}" ]]; then
    echo -e "  ${YELLOW}⚠${RESET} No token provided — get one from HA: Profile → Long-Lived Access Tokens"
    HA_TOKEN="your_long_lived_access_token_here"
  fi

  read -rp "  Pi hostname or IP [homeassistant.local]: " PI_HOST
  PI_HOST="${PI_HOST:-homeassistant.local}"

  read -rp "  Pi SSH user [root]: " PI_USER
  PI_USER="${PI_USER:-root}"

  read -rp "  Govee API Key (leave blank to skip): " GOVEE_API_KEY
  GOVEE_API_KEY="${GOVEE_API_KEY:-your_govee_api_key_here}"

  read -rp "  Anthropic API Key (for voice agent): " ANTHROPIC_API_KEY
  ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-your_anthropic_api_key_here}"

  read -rp "  ElevenLabs API Key (for TTS): " ELEVENLABS_API_KEY
  ELEVENLABS_API_KEY="${ELEVENLABS_API_KEY:-your_elevenlabs_api_key_here}"

  read -rp "  ElevenLabs Voice ID: " ELEVENLABS_VOICE_ID
  ELEVENLABS_VOICE_ID="${ELEVENLABS_VOICE_ID:-your_preferred_voice_id}"

  read -rp "  Voice PIN (4-6 digits for security): " AURA_VOICE_PIN
  AURA_VOICE_PIN="${AURA_VOICE_PIN:-change_me}"

  echo ""
  echo "  Generating .env file..."

  # Generate dashboard auth token
  if command -v openssl &>/dev/null; then
    DASHBOARD_AUTH_TOKEN=$(openssl rand -hex 32)
    echo -e "  ${GREEN}✓${RESET} Dashboard auth token auto-generated (64 chars)"
  else
    DASHBOARD_AUTH_TOKEN=""
    echo -e "  ${YELLOW}⚠${RESET} openssl not available — set DASHBOARD_AUTH_TOKEN manually"
  fi

  cat > "${ENV_FILE}" <<ENVEOF
# Home Assistant
HA_URL=${HA_URL}
HA_TOKEN=${HA_TOKEN}

# Govee LED API
GOVEE_API_KEY=${GOVEE_API_KEY}

# Spotify
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
SPOTIFY_REDIRECT_URI=http://localhost:8888/callback

# ElevenLabs TTS
ELEVENLABS_API_KEY=${ELEVENLABS_API_KEY}
ELEVENLABS_VOICE_ID=${ELEVENLABS_VOICE_ID}

# Claude API (for AURA voice agent intent processing)
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}

# Clap Detection
CLAP_WEBHOOK_SECRET=your_webhook_secret_here

# Network / Deployment
PI_HOST=${PI_HOST}
PI_USER=${PI_USER}

# Web Dashboard
NEXT_PUBLIC_HA_URL=${HA_URL}

# Adaptive Learning
AURA_DB_PATH=/config/aura/data/patterns.db
AURA_VOICE_PIN=${AURA_VOICE_PIN}

# Dashboard Authentication
DASHBOARD_AUTH_TOKEN=${DASHBOARD_AUTH_TOKEN}
ENVEOF

  chmod 600 "${ENV_FILE}"
  echo -e "  ${GREEN}✓${RESET} .env created at ${ENV_FILE} (chmod 600)"
fi

echo ""

# =============================================================================
# Step 3 — Test HA Connection
# =============================================================================
echo -e "${CYAN}━━━ Step 3/5: Home Assistant Connection ━━━${RESET}"
echo ""

# Reload env
if [[ -f "${ENV_FILE}" ]]; then
  set -o allexport
  source "${ENV_FILE}"
  set +o allexport
fi

HA_URL="${HA_URL:-http://homeassistant.local:8123}"
HA_TOKEN="${HA_TOKEN:-}"

if [[ "${HA_TOKEN}" == "your_"* || -z "${HA_TOKEN}" ]]; then
  echo -e "  ${YELLOW}⚠${RESET} HA_TOKEN is not set — skipping connection test"
  echo "  Set it in .env to enable this check."
else
  HTTP_STATUS=$(curl --silent --output /dev/null --write-out "%{http_code}" \
    --max-time 10 \
    -H "Authorization: Bearer ${HA_TOKEN}" \
    "${HA_URL}/api/" 2>/dev/null || echo "000")

  case "${HTTP_STATUS}" in
    200)
      echo -e "  ${GREEN}✓${RESET} Connected to Home Assistant at ${HA_URL}"
      ;;
    401)
      echo -e "  ${RED}✗${RESET} HA returned 401 — token may be invalid"
      echo "  Regenerate your Long-Lived Access Token in HA."
      ;;
    000)
      echo -e "  ${RED}✗${RESET} Cannot reach Home Assistant at ${HA_URL}"
      echo "  Check that the Pi is on, connected, and HA is running."
      ;;
    *)
      echo -e "  ${YELLOW}⚠${RESET} HA returned HTTP ${HTTP_STATUS}"
      ;;
  esac
fi

echo ""

# =============================================================================
# Step 4 — Test SSH to Pi
# =============================================================================
echo -e "${CYAN}━━━ Step 4/5: SSH Connection ━━━${RESET}"
echo ""

PI_HOST="${PI_HOST:-homeassistant.local}"
PI_USER="${PI_USER:-root}"

if ssh -o ConnectTimeout=5 -o BatchMode=yes \
    "${PI_USER}@${PI_HOST}" "echo 'ok'" &>/dev/null; then
  echo -e "  ${GREEN}✓${RESET} SSH to ${PI_USER}@${PI_HOST} — connected"
else
  echo -e "  ${YELLOW}⚠${RESET} Cannot SSH to ${PI_USER}@${PI_HOST}"
  echo "  Ensure SSH keys are set up:"
  echo "    ssh-copy-id ${PI_USER}@${PI_HOST}"
fi

echo ""

# =============================================================================
# Step 5 — Summary
# =============================================================================
echo -e "${CYAN}━━━ Step 5/5: Summary ━━━${RESET}"
echo ""
echo "  AURA setup wizard complete. Next steps:"
echo ""
echo -e "  ${BOLD}1. Deploy to Pi:${RESET}"
echo "     bash scripts/deploy/full_deploy.sh --restart --env --pip"
echo ""
echo -e "  ${BOLD}2. Start the dashboard:${RESET}"
echo "     cd dashboard && npm install && npm run dev"
echo ""
echo -e "  ${BOLD}3. Run security audit:${RESET}"
echo "     bash scripts/security_audit.sh"
echo ""
echo -e "  ${BOLD}4. Test a webhook:${RESET}"
echo "     bash scripts/test_webhook.sh double_clap"
echo ""
echo "  For the full setup guide: docs/SETUP_GUIDE.md"
echo ""
echo -e "${PURPLE}  Welcome to your AURA. ✦${RESET}"
echo ""
