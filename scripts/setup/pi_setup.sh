#!/usr/bin/env bash
# =============================================================================
# AURA by OASIS — pi_setup.sh
# First-time setup script for the Raspberry Pi running Home Assistant OS.
#
# IMPORTANT: Home Assistant OS is based on Buildroot. The SSH terminal add-on
# runs Alpine Linux. This script uses Alpine's package manager (apk), NOT
# apt-get or apt. Debian/Ubuntu package names will NOT work here.
#
# Run this script ON the Pi via the SSH & Web Terminal add-on AFTER:
#   1. Home Assistant OS is installed and running.
#   2. The SSH & Web Terminal add-on is installed with Protection Mode DISABLED
#      (required for systemctl access — Settings > Add-ons > SSH > Protection Mode).
#   3. This repo has been copied to /config/aura/ on the Pi via SCP:
#        scp -r . root@homeassistant.local:/config/aura/
#
# Usage (from the Pi terminal):
#   bash /config/aura/scripts/setup/pi_setup.sh
#
# To skip the optional voice agent steps:
#   SKIP_VOICE_AGENT=1 bash /config/aura/scripts/setup/pi_setup.sh
# =============================================================================

set -e  # Exit immediately on any command failure

# -----------------------------------------------------------------------------
# Banner
# -----------------------------------------------------------------------------
echo ""
echo "=============================================="
echo "  AURA by OASIS -- Pi Setup"
echo "  Ambient. Unified. Responsive. Automated."
echo "  (Alpine Linux / Home Assistant OS edition)"
echo "=============================================="
echo ""

# -----------------------------------------------------------------------------
# Guard: must be running on Linux
# -----------------------------------------------------------------------------
if [[ "$(uname -s)" != "Linux" ]]; then
  echo "ERROR: This script must be run on the Raspberry Pi (Linux)."
  echo "       Current OS: $(uname -s)"
  echo "       Open the SSH & Web Terminal add-on in Home Assistant."
  exit 1
fi

echo "[1/9] Platform check passed -- running on Linux."
echo ""

# -----------------------------------------------------------------------------
# Guard: Protection Mode check
# systemctl is only available when the SSH add-on's Protection Mode is OFF.
# If it's missing, warn loudly now rather than failing silently at step 6.
# -----------------------------------------------------------------------------
if ! command -v systemctl &>/dev/null; then
  echo "WARNING: systemctl is not available on this shell."
  echo "         This means Protection Mode is ENABLED on the SSH & Web Terminal"
  echo "         add-on. The service registration steps will be skipped."
  echo ""
  echo "         To enable systemd access:"
  echo "           Home Assistant > Settings > Add-ons > SSH & Web Terminal"
  echo "           > Toggle OFF 'Protection Mode' > Save > Restart add-on"
  echo ""
  echo "         Re-run this script after disabling Protection Mode."
  echo ""
  SYSTEMD_AVAILABLE=0
else
  SYSTEMD_AVAILABLE=1
  echo "[INFO]  systemctl found -- systemd service registration will proceed."
  echo ""
fi

# -----------------------------------------------------------------------------
# Paths
#
# On Home Assistant OS the only reliably writable directory across reboots is
# /config/ -- that is where HA stores its own YAML config. We install AURA
# there so everything survives OS updates.
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
AURA_DIR="/config/aura"
VENV_DIR="${AURA_DIR}/.venv"
REQUIREMENTS="${REPO_ROOT}/clap-trigger/requirements.txt"
SERVICE_SRC="${REPO_ROOT}/clap-trigger/clap_service.service"
SERVICE_DEST="/etc/systemd/system/clap_service.service"

echo "Repo root : ${REPO_ROOT}"
echo "Aura dir  : ${AURA_DIR}"
echo "Venv dir  : ${VENV_DIR}"
echo ""

# -----------------------------------------------------------------------------
# Step 2 -- Update Alpine package index
# apk update refreshes the index of available packages from the Alpine mirrors.
# This is the Alpine equivalent of `apt-get update`.
# -----------------------------------------------------------------------------
echo "[2/9] Updating Alpine package index..."
apk update
echo "      Done."
echo ""

# -----------------------------------------------------------------------------
# Step 3 -- Install system dependencies via apk
#
# Alpine package names differ from Debian. Correct mappings used here:
#   python3          -- Python 3 runtime (same name on Alpine)
#   py3-pip          -- pip for Python 3 (NOT python3-pip)
#   portaudio-dev    -- C headers for PyAudio (NOT portaudio19-dev)
#   gcc              -- C compiler needed to build PyAudio from source
#   python3-dev      -- Python C headers (needed for C extension modules)
#   musl-dev         -- Alpine's libc headers (needed for C compilation)
#   alsa-utils       -- arecord / aplay for mic testing
#   git              -- for pulling updates later
#
# Note: python3-venv is not a separate package on Alpine -- venv is included
# in the python3 package itself when py3-pip is present.
# -----------------------------------------------------------------------------
echo "[3/9] Installing system dependencies (Alpine packages)..."
apk add --no-cache \
  python3 \
  py3-pip \
  portaudio-dev \
  gcc \
  python3-dev \
  musl-dev \
  alsa-utils \
  git
echo "      Installed: python3, py3-pip, portaudio-dev, gcc, python3-dev, musl-dev, alsa-utils, git"
echo ""

# -----------------------------------------------------------------------------
# Step 4 -- Create the AURA working directory and Python virtual environment
#
# We use a venv to isolate AURA's Python packages from the system Python.
# This avoids conflicts if Alpine's system Python packages are updated.
# -----------------------------------------------------------------------------
echo "[4/9] Creating Python virtual environment at ${VENV_DIR}..."
mkdir -p "${AURA_DIR}"
python3 -m venv "${VENV_DIR}"
echo "      Virtual environment created."
echo ""

# -----------------------------------------------------------------------------
# Step 5 -- Install Python dependencies from clap-trigger/requirements.txt
#
# PyAudio compiles a C extension and links against portaudio -- that is why
# gcc, python3-dev, musl-dev, and portaudio-dev were installed above.
# -----------------------------------------------------------------------------
echo "[5/9] Installing Python dependencies from clap-trigger/requirements.txt..."

if [[ ! -f "${REQUIREMENTS}" ]]; then
  echo "ERROR: requirements.txt not found at ${REQUIREMENTS}"
  echo "       Make sure the repo was copied to /config/aura/ on the Pi:"
  echo "         scp -r . root@homeassistant.local:/config/aura/"
  exit 1
fi

"${VENV_DIR}/bin/pip" install --quiet --upgrade pip
"${VENV_DIR}/bin/pip" install --quiet -r "${REQUIREMENTS}"
echo "      Dependencies installed from ${REQUIREMENTS}"
echo ""

# -----------------------------------------------------------------------------
# Step 6 -- Register the clap_service systemd unit
#
# The service file tells systemd how to launch clap_listener.py at boot and
# restart it if it crashes. We enable it (auto-start on boot) but do NOT
# start it yet -- the operator should verify mic levels first.
#
# Requires Protection Mode OFF on the SSH add-on (checked at the top).
# -----------------------------------------------------------------------------
echo "[6/9] Registering clap_service with systemd..."

if [[ "${SYSTEMD_AVAILABLE}" -eq 0 ]]; then
  echo "      SKIPPED -- systemctl not available (Protection Mode is ON)."
  echo "      Disable Protection Mode on the SSH add-on and re-run to register"
  echo "      the service."
else
  if [[ ! -f "${SERVICE_SRC}" ]]; then
    echo "ERROR: Service file not found at ${SERVICE_SRC}"
    echo "       Make sure clap-trigger/clap_service.service exists in the repo."
    exit 1
  fi

  cp "${SERVICE_SRC}" "${SERVICE_DEST}"
  chmod 644 "${SERVICE_DEST}"

  # Reload daemon so it picks up the new unit file, then enable for auto-start
  # on boot -- but do NOT start it so the operator can verify config first.
  systemctl daemon-reload
  systemctl enable clap_service
  echo "      Service file copied to ${SERVICE_DEST}"
  echo "      clap_service enabled (will auto-start on next boot)."
fi
echo ""

# -----------------------------------------------------------------------------
# Step 7 (Voice Agent -- OPTIONAL) -- Additional system dependencies
#
# Skip this entire section by setting SKIP_VOICE_AGENT=1:
#   SKIP_VOICE_AGENT=1 bash pi_setup.sh
#
# Alpine package names for voice agent deps:
#   openblas-dev  -- OpenBLAS headers for NumPy/faster-whisper (NOT libopenblas-dev)
#   ffmpeg        -- Audio format conversion for faster-whisper (same name on Alpine)
#   libsndfile    -- C library for audio file I/O (NOT libsndfile1)
# -----------------------------------------------------------------------------
if [[ "${SKIP_VOICE_AGENT:-0}" == "1" ]]; then
  echo "[7/9] Skipping voice agent system dependencies (SKIP_VOICE_AGENT=1)."
else
  echo "[7/9] Installing voice agent system dependencies..."
  apk add --no-cache \
    openblas-dev \
    ffmpeg \
    libsndfile
  echo "      Installed: openblas-dev, ffmpeg, libsndfile"
fi
echo ""

# -----------------------------------------------------------------------------
# Step 8 (Voice Agent -- OPTIONAL) -- Voice agent Python packages and service
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

  if [[ "${SYSTEMD_AVAILABLE}" -eq 0 ]]; then
    echo "      SKIPPED service registration -- systemctl not available."
    echo "      Disable Protection Mode and re-run to register aura_voice."
  elif [[ ! -f "${VOICE_SERVICE_SRC}" ]]; then
    echo "      WARN: Voice agent service file not found at ${VOICE_SERVICE_SRC}"
    echo "            Skipping voice agent service registration."
  else
    cp "${VOICE_SERVICE_SRC}" "${VOICE_SERVICE_DEST}"
    chmod 644 "${VOICE_SERVICE_DEST}"
    systemctl daemon-reload
    # Enable for auto-start on boot but do NOT start -- the operator must
    # populate ANTHROPIC_API_KEY and ELEVENLABS_API_KEY in .env first.
    systemctl enable aura_voice
    echo "      aura_voice.service registered and enabled."
    echo "      It will NOT start until you populate ANTHROPIC_API_KEY and"
    echo "      ELEVENLABS_API_KEY in ${AURA_DIR}/.env, then run:"
    echo "        systemctl start aura_voice"
  fi
fi
echo ""

# -----------------------------------------------------------------------------
# Step 9 -- Sanity check: confirm core Python packages are importable
# -----------------------------------------------------------------------------
echo "[9/9] Verifying core Python package imports..."
"${VENV_DIR}/bin/python3" -c "import pyaudio, numpy, requests, yaml" \
  && echo "      All required Python packages import successfully." \
  || {
    echo "ERROR: One or more packages failed to import."
    echo "       Check the pip output above for compilation errors."
    echo "       Ensure gcc, python3-dev, musl-dev, and portaudio-dev are installed."
    exit 1
  }
echo ""

# -----------------------------------------------------------------------------
# Done -- print next steps
# -----------------------------------------------------------------------------
echo "=============================================="
echo "  Setup complete!"
echo "=============================================="
echo ""
echo "Next steps:"
echo ""
echo "  1. Copy .env to the Pi (run from your desktop):"
echo "     scp .env root@homeassistant.local:${AURA_DIR}/.env"
echo ""
echo "  2. Verify the full installation:"
echo "     bash ${SCRIPT_DIR}/verify_install.sh"
echo ""
echo "  3. Test mic input levels before starting the service:"
echo "     arecord -l          (list recording devices)"
echo "     arecord -d 3 /tmp/test.wav && aplay /tmp/test.wav"
echo ""
echo "  4. Start the clap detection service:"
echo "     systemctl start clap_service"
echo ""
echo "  5. Watch live logs:"
echo "     journalctl -u clap_service -f"
echo ""
echo "  6. Test a webhook manually:"
echo "     curl -X POST http://homeassistant.local:8123/api/webhook/aura_double_clap"
echo ""
echo "  NOTE: If systemd steps were skipped, disable Protection Mode on the"
echo "  SSH & Web Terminal add-on and re-run this script."
echo ""
