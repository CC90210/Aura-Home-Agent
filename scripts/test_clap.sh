#!/usr/bin/env bash
# =============================================================================
# AURA by OASIS — test_clap.sh
# Dry-run tester for clap detection mic input levels.
#
# Activates the Python virtual environment and runs clap_listener.py with the
# --test flag, which records audio for 5 seconds and reports the peak amplitude
# levels seen on the microphone. Use this to:
#
#   - Confirm the USB microphone is being picked up by Python/PyAudio
#   - Find a good value for the clap threshold in config.yaml
#   - Verify that background noise is well below clap levels
#
# How to calibrate:
#   1. Run this script in silence — note the ambient peak level
#   2. Run it again and clap once — note the clap peak level
#   3. Set threshold in clap-trigger/config.yaml to roughly halfway between
#
# Usage (run ON the Pi via SSH):
#   bash scripts/test_clap.sh
#
# Options:
#   --duration <seconds>   How long to listen (default: 5)
#   --device   <index>     PyAudio device index to test (default: auto-detect)
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Resolve paths
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"

AURA_DIR="/home/pi/aura"
VENV_DIR="${AURA_DIR}/.venv"
CLAP_SCRIPT="${REPO_ROOT}/clap-trigger/clap_listener.py"

# -----------------------------------------------------------------------------
# Parse optional flags
# -----------------------------------------------------------------------------
DURATION=5
DEVICE_ARG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --duration)
      DURATION="$2"
      shift 2
      ;;
    --device)
      DEVICE_ARG="--device $2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1"
      echo "Usage: $0 [--duration <seconds>] [--device <index>]"
      exit 1
      ;;
  esac
done

echo ""
echo "=============================================="
echo "  AURA by OASIS — Clap Detection Tester"
echo "=============================================="
echo ""

# -----------------------------------------------------------------------------
# Load .env if present (in case clap_listener.py reads env vars)
# -----------------------------------------------------------------------------
if [[ -f "${ENV_FILE}" ]]; then
  set -o allexport
  # shellcheck source=/dev/null
  source "${ENV_FILE}"
  set +o allexport
fi

# -----------------------------------------------------------------------------
# Verify virtual environment exists
# -----------------------------------------------------------------------------
if [[ ! -d "${VENV_DIR}" ]]; then
  echo "ERROR: Virtual environment not found at ${VENV_DIR}"
  echo "       Run scripts/setup/pi_setup.sh on the Pi first."
  exit 1
fi

PYTHON="${VENV_DIR}/bin/python3"
if [[ ! -x "${PYTHON}" ]]; then
  echo "ERROR: Python binary not found at ${PYTHON}"
  exit 1
fi

echo "Using Python : ${PYTHON}"
echo "Venv         : ${VENV_DIR}"
echo ""

# -----------------------------------------------------------------------------
# Verify clap_listener.py exists
# -----------------------------------------------------------------------------
if [[ ! -f "${CLAP_SCRIPT}" ]]; then
  echo "ERROR: clap_listener.py not found at ${CLAP_SCRIPT}"
  echo "       Make sure the clap-trigger/ directory is populated."
  exit 1
fi

# -----------------------------------------------------------------------------
# Quick PyAudio sanity check — list available audio devices
# -----------------------------------------------------------------------------
echo "Available audio input devices:"
echo "----------------------------------------------"
"${PYTHON}" - <<'EOF'
import sys
try:
    import pyaudio
    pa = pyaudio.PyAudio()
    found_input = False
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        if info.get("maxInputChannels", 0) > 0:
            print(f"  Device {i}: {info['name']}")
            print(f"           Channels: {int(info['maxInputChannels'])}  |  "
                  f"Sample rate: {int(info['defaultSampleRate'])} Hz")
            found_input = True
    if not found_input:
        print("  No input devices found! Plug in your USB microphone.")
        sys.exit(1)
    pa.terminate()
except ImportError:
    print("  ERROR: pyaudio not installed in the venv.")
    sys.exit(1)
EOF
echo "----------------------------------------------"
echo ""

# -----------------------------------------------------------------------------
# Run clap_listener.py in --test mode
# This runs a short recording session, reports amplitude peaks, and exits.
# It does NOT fire any webhooks.
# -----------------------------------------------------------------------------
echo "Listening for ${DURATION} seconds..."
echo "Clap now to calibrate your threshold!"
echo ""

# shellcheck disable=SC2086
"${PYTHON}" "${CLAP_SCRIPT}" --test --duration "${DURATION}" ${DEVICE_ARG}
STATUS=$?

echo ""
if [[ "${STATUS}" -eq 0 ]]; then
  echo "Test complete."
  echo ""
  echo "Next steps:"
  echo "  - Compare the ambient peak vs clap peak shown above"
  echo "  - Set 'threshold' in clap-trigger/config.yaml to a value between them"
  echo "  - Start the live service: systemctl start clap_service"
else
  echo "Test exited with status ${STATUS}."
  echo "Check the output above for errors."
  exit "${STATUS}"
fi
echo ""
