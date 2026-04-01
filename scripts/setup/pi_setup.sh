#!/usr/bin/env bash
# =============================================================================
# AURA by OASIS — pi_setup.sh
# First-time setup script for the Raspberry Pi running Home Assistant OS.
#
# Run this script ON the Pi via SSH after Home Assistant is already installed
# and running. It installs the clap detection dependencies and registers
# the systemd service that fires webhooks into Home Assistant.
#
# Usage:
#   ssh root@homeassistant.local
#   bash pi_setup.sh
# =============================================================================

set -e  # Exit immediately on any command failure

# -----------------------------------------------------------------------------
# Banner
# -----------------------------------------------------------------------------
echo ""
echo "=============================================="
echo "  AURA by OASIS — Pi Setup"
echo "  Ambient. Unified. Responsive. Automated."
echo "=============================================="
echo ""

# -----------------------------------------------------------------------------
# Guard: must be running on Linux
# -----------------------------------------------------------------------------
if [[ "$(uname -s)" != "Linux" ]]; then
  echo "ERROR: This script must be run on the Raspberry Pi (Linux)."
  echo "       Current OS: $(uname -s)"
  echo "       SSH into the Pi first: ssh root@homeassistant.local"
  exit 1
fi

echo "[1/9] Platform check passed — running on Linux."
echo ""

# -----------------------------------------------------------------------------
# Resolve the repo root relative to this script so paths stay correct even if
# the repo is cloned to a non-standard location.
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
AURA_DIR="/home/pi/aura"
VENV_DIR="${AURA_DIR}/.venv"
REQUIREMENTS="${REPO_ROOT}/clap-trigger/requirements.txt"
SERVICE_SRC="${REPO_ROOT}/clap-trigger/clap_service.service"
SERVICE_DEST="/etc/systemd/system/clap_service.service"

echo "Repo root : ${REPO_ROOT}"
echo "Aura dir  : ${AURA_DIR}"
echo "Venv dir  : ${VENV_DIR}"
echo ""

# -----------------------------------------------------------------------------
# Step 1 — Update package index
# -----------------------------------------------------------------------------
echo "[2/9] Updating system package list..."
apt-get update -qq
echo "      Done."
echo ""

# -----------------------------------------------------------------------------
# Step 2 — Install system dependencies
#   python3        : runtime for clap_listener.py
#   python3-pip    : package installer
#   python3-venv   : isolated environment so we don't pollute system Python
#   portaudio19-dev: C library required by PyAudio to talk to ALSA
#   git            : needed if scripts pull updates later
# -----------------------------------------------------------------------------
echo "[3/9] Installing system dependencies..."
apt-get install -y -qq \
  python3 \
  python3-pip \
  python3-venv \
  portaudio19-dev \
  git
echo "      Installed: python3, pip, venv, portaudio19-dev, git"
echo ""

# -----------------------------------------------------------------------------
# Step 3 — Create the aura working directory and Python virtual environment
# -----------------------------------------------------------------------------
echo "[4/9] Creating Python virtual environment at ${VENV_DIR}..."
mkdir -p "${AURA_DIR}"
python3 -m venv "${VENV_DIR}"
echo "      Virtual environment created."
echo ""

# -----------------------------------------------------------------------------
# Step 4 — Install Python dependencies from requirements.txt
# -----------------------------------------------------------------------------
echo "[5/9] Installing Python dependencies..."

if [[ ! -f "${REQUIREMENTS}" ]]; then
  echo "ERROR: requirements.txt not found at ${REQUIREMENTS}"
  echo "       Make sure the repo is cloned at ${REPO_ROOT}"
  exit 1
fi

"${VENV_DIR}/bin/pip" install --quiet --upgrade pip
"${VENV_DIR}/bin/pip" install --quiet -r "${REQUIREMENTS}"
echo "      Dependencies installed from ${REQUIREMENTS}"
echo ""

# -----------------------------------------------------------------------------
# Step 5 — Copy systemd service file
# The service file tells systemd how to launch clap_listener.py at boot and
# restart it automatically if it crashes.
# -----------------------------------------------------------------------------
echo "[6/9] Registering clap_service with systemd..."

if [[ ! -f "${SERVICE_SRC}" ]]; then
  echo "ERROR: Service file not found at ${SERVICE_SRC}"
  echo "       Make sure clap-trigger/clap_service.service exists in the repo."
  exit 1
fi

cp "${SERVICE_SRC}" "${SERVICE_DEST}"
chmod 644 "${SERVICE_DEST}"

# Reload daemon so it picks up the new unit file, then enable for auto-start
# on boot — but do NOT start it yet so the operator can verify config first.
systemctl daemon-reload
systemctl enable clap_service
echo "      Service file copied to ${SERVICE_DEST}"
echo "      clap_service enabled (will start on next boot)."
echo ""

# -----------------------------------------------------------------------------
# Step 6 (Voice Agent — OPTIONAL) — Install additional system dependencies
#
# NOTE: This section is optional. If you do not have an ElevenLabs API key yet,
# or do not plan to use the voice agent, you can safely skip steps 7 and 8 by
# setting SKIP_VOICE_AGENT=1 in your environment before running this script:
#   SKIP_VOICE_AGENT=1 bash pi_setup.sh
#
# Additional packages:
#   libopenblas-dev : faster-whisper and NumPy rely on OpenBLAS for BLAS routines
#   ffmpeg          : audio format conversion used by faster-whisper and soundfile
#   libsndfile1     : C library backing the soundfile/pysndfile Python packages
# -----------------------------------------------------------------------------
if [[ "${SKIP_VOICE_AGENT:-0}" == "1" ]]; then
  echo "[7/9] Skipping voice agent system deps (SKIP_VOICE_AGENT=1)."
else
  echo "[7/9] Installing voice agent system dependencies..."
  apt-get install -y -qq \
    libopenblas-dev \
    ffmpeg \
    libsndfile1
  echo "      Installed: libopenblas-dev, ffmpeg, libsndfile1"
fi
echo ""

# -----------------------------------------------------------------------------
# Step 7 (Voice Agent — OPTIONAL) — Install voice-agent Python packages and
# register the aura_voice systemd service.
# -----------------------------------------------------------------------------
VOICE_REQUIREMENTS="${REPO_ROOT}/voice-agent/requirements.txt"
VOICE_SERVICE_SRC="${REPO_ROOT}/voice-agent/aura_voice.service"
VOICE_SERVICE_DEST="/etc/systemd/system/aura_voice.service"

if [[ "${SKIP_VOICE_AGENT:-0}" == "1" ]]; then
  echo "[8/9] Skipping voice agent Python install (SKIP_VOICE_AGENT=1)."
else
  echo "[8/9] Installing voice agent Python dependencies and registering service..."

  if [[ ! -f "${VOICE_REQUIREMENTS}" ]]; then
    echo "      WARN: voice-agent/requirements.txt not found at ${VOICE_REQUIREMENTS}"
    echo "            Skipping voice agent Python install."
  else
    "${VENV_DIR}/bin/pip" install --quiet -r "${VOICE_REQUIREMENTS}"
    echo "      Voice agent dependencies installed from ${VOICE_REQUIREMENTS}"
  fi

  if [[ ! -f "${VOICE_SERVICE_SRC}" ]]; then
    echo "      WARN: voice agent service file not found at ${VOICE_SERVICE_SRC}"
    echo "            Skipping voice agent service registration."
  else
    cp "${VOICE_SERVICE_SRC}" "${VOICE_SERVICE_DEST}"
    chmod 644 "${VOICE_SERVICE_DEST}"
    systemctl daemon-reload
    # Enable for auto-start on boot but do NOT start — the operator must supply
    # ANTHROPIC_API_KEY and ELEVENLABS_API_KEY in .env before starting.
    systemctl enable aura_voice
    echo "      aura_voice.service registered and enabled."
    echo "      It will NOT start until you populate ANTHROPIC_API_KEY and"
    echo "      ELEVENLABS_API_KEY in ${AURA_DIR}/.env, then run:"
    echo "        systemctl start aura_voice"
  fi
fi
echo ""

# -----------------------------------------------------------------------------
# Step 8 — Sanity check: confirm Python packages are importable
# -----------------------------------------------------------------------------
echo "[9/9] Verifying installation..."
"${VENV_DIR}/bin/python3" -c "import pyaudio, numpy, requests, yaml" \
  && echo "      All required Python packages import successfully." \
  || { echo "ERROR: One or more packages failed to import. Check pip output above."; exit 1; }
echo ""

# -----------------------------------------------------------------------------
# Done — print next steps
# -----------------------------------------------------------------------------
echo "=============================================="
echo "  Setup complete!"
echo "=============================================="
echo ""
echo "Next steps:"
echo ""
echo "  1. Copy .env to the Pi:"
echo "     scp .env root@homeassistant.local:${AURA_DIR}/.env"
echo ""
echo "  2. Verify the installation:"
echo "     bash scripts/setup/verify_install.sh   (run from your desktop)"
echo "     OR on the Pi: bash ${SCRIPT_DIR}/verify_install.sh"
echo ""
echo "  3. Test mic input levels before starting the service:"
echo "     bash scripts/test_clap.sh"
echo ""
echo "  4. Start the clap detection service:"
echo "     ssh root@homeassistant.local 'systemctl start clap_service'"
echo ""
echo "  5. Watch live logs:"
echo "     ssh root@homeassistant.local 'journalctl -u clap_service -f'"
echo ""
echo "  6. Test a webhook manually:"
echo "     bash scripts/test_webhook.sh double_clap"
echo ""
