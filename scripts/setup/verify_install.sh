#!/usr/bin/env bash
# =============================================================================
# AURA by OASIS — verify_install.sh
# Post-setup verification script.
#
# Checks every critical component and prints a PASS/FAIL for each one, then
# exits with a non-zero code if anything is wrong so it can be used in CI or
# deployment pipelines.
#
# Can be run from your desktop (checks HA reachability over the network) OR
# from the Pi itself (checks local venv, mic, and systemd).
#
# Usage:
#   bash scripts/setup/verify_install.sh
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Resolve repo root so we can find .env regardless of where the script is called
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

ENV_FILE="${REPO_ROOT}/.env"
AURA_DIR="/home/pi/aura"
VENV_DIR="${AURA_DIR}/.venv"

# Counters for summary
PASS=0
FAIL=0
SKIP=0

# -----------------------------------------------------------------------------
# Helper: print a labelled result and increment counters
# -----------------------------------------------------------------------------
pass() {
  echo "  [PASS] $1"
  PASS=$((PASS + 1))
}

fail() {
  echo "  [FAIL] $1"
  FAIL=$((FAIL + 1))
}

skip() {
  echo "  [SKIP] $1"
  SKIP=$((SKIP + 1))
}

# -----------------------------------------------------------------------------
# Load .env if it exists so HA_URL is available for network checks
# -----------------------------------------------------------------------------
if [[ -f "${ENV_FILE}" ]]; then
  # Export only lines that look like KEY=value (skip comments and blanks)
  set -o allexport
  # shellcheck source=/dev/null
  source "${ENV_FILE}"
  set +o allexport
fi

echo ""
echo "=============================================="
echo "  AURA by OASIS — Installation Verification"
echo "=============================================="
echo ""

# =============================================================================
# CHECK 1: .env file exists and contains the minimum required variables
# =============================================================================
echo "[ Checking .env file ]"

REQUIRED_VARS=(HA_URL HA_TOKEN PI_HOST PI_USER GOVEE_API_KEY)

if [[ -f "${ENV_FILE}" ]]; then
  pass ".env file exists at ${ENV_FILE}"

  for var in "${REQUIRED_VARS[@]}"; do
    value="${!var:-}"
    if [[ -n "${value}" && "${value}" != "your_"* ]]; then
      pass "  \$${var} is set"
    else
      fail "  \$${var} is missing or still has placeholder value"
    fi
  done
else
  fail ".env file NOT found at ${ENV_FILE} — copy .env.example and fill it in"
  # Without the env file we can't do network checks, but continue to report all
fi

echo ""

# =============================================================================
# CHECK 2: Home Assistant is reachable
# =============================================================================
echo "[ Checking Home Assistant reachability ]"

HA_URL="${HA_URL:-http://homeassistant.local:8123}"
HA_CHECK_URL="${HA_URL}/api/"

if command -v curl &>/dev/null; then
  HTTP_STATUS=$(curl --silent --output /dev/null --write-out "%{http_code}" \
    --max-time 10 "${HA_CHECK_URL}" 2>/dev/null || echo "000")

  if [[ "${HTTP_STATUS}" == "200" || "${HTTP_STATUS}" == "401" ]]; then
    # 401 means HA is up but we hit an auth-protected endpoint — that's fine
    pass "Home Assistant is reachable at ${HA_URL} (HTTP ${HTTP_STATUS})"
  else
    fail "Home Assistant not reachable at ${HA_URL} (HTTP ${HTTP_STATUS})"
    echo "       Make sure the Pi is powered on and connected to the network."
  fi
else
  fail "curl is not installed — cannot check HA reachability"
fi

echo ""

# =============================================================================
# CHECK 3: Python virtual environment exists and has required packages
# (This check only makes sense when running ON the Pi)
# =============================================================================
echo "[ Checking Python virtual environment ]"

if [[ -d "${VENV_DIR}" ]]; then
  pass "Virtual environment exists at ${VENV_DIR}"

  PYTHON="${VENV_DIR}/bin/python3"
  if [[ -x "${PYTHON}" ]]; then
    pass "  Python binary found: ${PYTHON}"

    REQUIRED_PACKAGES=(pyaudio numpy requests yaml)
    for pkg in "${REQUIRED_PACKAGES[@]}"; do
      if "${PYTHON}" -c "import ${pkg}" &>/dev/null; then
        pass "  Python package '${pkg}' is importable"
      else
        fail "  Python package '${pkg}' is NOT importable — run pi_setup.sh again"
      fi
    done
  else
    fail "  Python binary not found at ${PYTHON}"
  fi
else
  fail "Virtual environment NOT found at ${VENV_DIR}"
  echo "       Run scripts/setup/pi_setup.sh on the Pi first."
  echo "       (If verifying from your desktop, this check is expected to fail.)"
fi

echo ""

# =============================================================================
# CHECK 4: USB microphone is detected
# (Only meaningful on the Pi — arecord is an ALSA utility)
# =============================================================================
echo "[ Checking USB microphone ]"

if command -v arecord &>/dev/null; then
  MIC_COUNT=$(arecord -l 2>/dev/null | grep -c "card" || true)
  if [[ "${MIC_COUNT}" -gt 0 ]]; then
    pass "USB microphone detected (${MIC_COUNT} recording device(s) found)"
    # Print the device list for reference
    arecord -l 2>/dev/null | grep "card" | while read -r line; do
      echo "       ${line}"
    done
  else
    fail "No recording devices found — plug in the USB microphone"
  fi
else
  fail "arecord not available — this check must be run on the Pi (ALSA not installed here)"
  echo "       Install with: apt-get install -y alsa-utils"
fi

echo ""

# =============================================================================
# CHECK 5: clap_service is registered with systemd
# (Only meaningful on the Pi)
# =============================================================================
echo "[ Checking systemd service ]"

if command -v systemctl &>/dev/null; then
  if systemctl list-unit-files clap_service.service &>/dev/null | grep -q "clap_service"; then
    SERVICE_STATE=$(systemctl is-enabled clap_service 2>/dev/null || echo "unknown")
    pass "clap_service.service is registered with systemd (state: ${SERVICE_STATE})"

    # Check if it's currently running
    if systemctl is-active --quiet clap_service 2>/dev/null; then
      pass "  clap_service is currently RUNNING"
    else
      echo "       clap_service is not running (start with: systemctl start clap_service)"
    fi
  else
    fail "clap_service.service is NOT registered — run pi_setup.sh on the Pi"
  fi
else
  fail "systemctl not available — this check must be run on the Pi"
fi

echo ""

# =============================================================================
# CHECK 6 (OPTIONAL): Voice agent dependencies and configuration
#
# These checks are advisory. Missing voice agent setup prints [SKIP], not
# [FAIL], so the script still exits 0 if everything else is green. The voice
# agent requires ANTHROPIC_API_KEY and ELEVENLABS_API_KEY in .env, plus the
# Python packages installed by pi_setup.sh step 7/8.
# =============================================================================
echo "[ Checking voice agent (optional) ]"

# --- Python packages ---
if [[ -d "${VENV_DIR}" && -x "${VENV_DIR}/bin/python3" ]]; then
  PYTHON="${VENV_DIR}/bin/python3"
  VOICE_PACKAGES=(openwakeword faster_whisper anthropic elevenlabs)
  for pkg in "${VOICE_PACKAGES[@]}"; do
    if "${PYTHON}" -c "import ${pkg}" &>/dev/null; then
      pass "  Voice agent Python package '${pkg}' is importable"
    else
      skip "  Voice agent Python package '${pkg}' not installed — run pi_setup.sh without SKIP_VOICE_AGENT=1"
    fi
  done
else
  skip "  Virtual environment not found — skipping voice agent package checks"
fi

# --- API keys ---
ANTHROPIC_KEY="${ANTHROPIC_API_KEY:-}"
if [[ -n "${ANTHROPIC_KEY}" && "${ANTHROPIC_KEY}" != "your_"* ]]; then
  pass "  \$ANTHROPIC_API_KEY is set"
else
  skip "  \$ANTHROPIC_API_KEY is not set — required for voice agent intent processing"
fi

ELEVENLABS_KEY="${ELEVENLABS_API_KEY:-}"
if [[ -n "${ELEVENLABS_KEY}" && "${ELEVENLABS_KEY}" != "your_"* ]]; then
  pass "  \$ELEVENLABS_API_KEY is set"
else
  skip "  \$ELEVENLABS_API_KEY is not set — required for voice agent TTS responses"
fi

# --- systemd service ---
if command -v systemctl &>/dev/null; then
  if systemctl list-unit-files aura_voice.service &>/dev/null | grep -q "aura_voice"; then
    VOICE_SERVICE_STATE=$(systemctl is-enabled aura_voice 2>/dev/null || echo "unknown")
    pass "  aura_voice.service is registered with systemd (state: ${VOICE_SERVICE_STATE})"

    if systemctl is-active --quiet aura_voice 2>/dev/null; then
      pass "  aura_voice is currently RUNNING"
    else
      echo "       aura_voice is not running (start with: systemctl start aura_voice)"
    fi
  else
    skip "  aura_voice.service is not registered — run pi_setup.sh without SKIP_VOICE_AGENT=1"
  fi
else
  skip "  systemctl not available — voice agent service check must be run on the Pi"
fi

echo ""

# =============================================================================
# CHECK 7 (OPTIONAL): Learning module files
#
# These checks are advisory. Missing learning module files print [SKIP], not
# [FAIL], so the script still exits 0 if everything else is green. The learning
# modules are installed separately and are not required for core AURA operation.
# =============================================================================
echo "[ Checking learning modules (optional) ]"

LEARNING_FILES=(
  "learning/pattern_engine.py"
  "learning/habit_tracker.py"
  "learning/config.yaml"
  "voice-agent/personality.yaml"
)

for rel_path in "${LEARNING_FILES[@]}"; do
  full_path="${AURA_DIR}/${rel_path}"
  if [[ -f "${full_path}" ]]; then
    pass "  ${rel_path} exists"
  else
    skip "  ${rel_path} not found — learning modules not yet deployed"
  fi
done

echo ""

# =============================================================================
# Summary
# =============================================================================
TOTAL=$((PASS + FAIL + SKIP))
echo "=============================================="
echo "  Verification Summary"
echo "=============================================="
echo "  Total checks : ${TOTAL}"
echo "  Passed       : ${PASS}"
echo "  Failed       : ${FAIL}"
echo "  Skipped      : ${SKIP}"
echo "=============================================="
echo ""

if [[ "${FAIL}" -gt 0 ]]; then
  echo "Some checks failed. Address the issues above before proceeding."
  echo ""
  exit 1
else
  echo "All required checks passed. AURA is ready."
  if [[ "${SKIP}" -gt 0 ]]; then
    echo "(${SKIP} optional check(s) skipped — see above for details.)"
  fi
  echo ""
  exit 0
fi
