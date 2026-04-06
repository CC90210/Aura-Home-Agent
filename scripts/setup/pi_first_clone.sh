#!/usr/bin/env bash
# =============================================================================
# AURA by OASIS — pi_first_clone.sh
# First-time bootstrap script for a FRESH Raspberry Pi running Home Assistant OS.
#
# This script runs ONCE — it clones the repo, creates the Python venv, installs
# all dependencies, registers systemd services, and prepares the environment.
# All future updates from the desktop use quick_update.sh (git pull + restart).
#
# DIFFERENCE from pi_setup.sh:
#   pi_setup.sh   — assumes the repo was SCP'd to the Pi beforehand.
#   pi_first_clone.sh — THIS SCRIPT — clones the repo from GitHub directly.
#   Run this script instead of pi_setup.sh when setting up a fresh Pi.
#
# PREREQUISITES (do these before running this script):
#   1. Home Assistant OS is installed and accessible at homeassistant.local:8123
#   2. The "SSH & Web Terminal" add-on is installed with Protection Mode DISABLED:
#        Settings > Add-ons > SSH & Web Terminal > Protection Mode → OFF > Save > Restart add-on
#      (Protection Mode must be OFF for systemctl access.)
#   3. SSH into the Pi:
#        ssh root@homeassistant.local
#   4. Paste or run this script:
#        curl -fsSL https://raw.githubusercontent.com/CC90210/Aura-Home-Agent/main/scripts/setup/pi_first_clone.sh | bash
#      OR copy it manually and run:
#        bash /tmp/pi_first_clone.sh
#
# IDEMPOTENT: safe to run more than once. Existing repo, venv, and service
# registrations are detected and skipped rather than overwritten.
#
# SKIP FLAGS:
#   SKIP_VOICE_AGENT=1 bash pi_first_clone.sh   — omit voice agent steps
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Color helpers
# Wrap output in ANSI codes so the terminal is easy to scan at a glance.
# Use plain echo (no -e) — Alpine's /bin/sh supports $'...' escape sequences,
# but we explicitly use \033 codes via printf for maximum portability.
# -----------------------------------------------------------------------------
_RED='\033[0;31m'
_GREEN='\033[0;32m'
_YELLOW='\033[1;33m'
_CYAN='\033[0;36m'
_BOLD='\033[1m'
_RESET='\033[0m'

info()    { printf "${_CYAN}[INFO]${_RESET}  %s\n" "$*"; }
ok()      { printf "${_GREEN}[ OK ]${_RESET}  %s\n" "$*"; }
warn()    { printf "${_YELLOW}[WARN]${_RESET}  %s\n" "$*"; }
err()     { printf "${_RED}[ERR ]${_RESET}  %s\n" "$*" >&2; }
step()    { printf "\n${_BOLD}%s${_RESET}\n" "$*"; }
banner()  { printf "${_CYAN}%s${_RESET}\n" "$*"; }

# -----------------------------------------------------------------------------
# Banner
# -----------------------------------------------------------------------------
echo ""
banner "=================================================="
banner "  AURA by OASIS — First-Time Pi Setup"
banner "  Ambient. Unified. Responsive. Automated."
banner "  (Alpine Linux / Home Assistant OS edition)"
banner "=================================================="
echo ""

# -----------------------------------------------------------------------------
# Guard: must be running on Linux (not accidentally run on the desktop)
# -----------------------------------------------------------------------------
if [[ "$(uname -s)" != "Linux" ]]; then
  err "This script must be run on the Raspberry Pi (Linux)."
  err "Current OS: $(uname -s)"
  err "Open the SSH & Web Terminal add-on in Home Assistant and run it there."
  exit 1
fi
ok "Platform check passed — running on Linux."

# -----------------------------------------------------------------------------
# Guard: Protection Mode check
# systemctl is only available when the SSH add-on's Protection Mode is OFF.
# Warn loudly now rather than failing silently during service registration.
# -----------------------------------------------------------------------------
if ! command -v systemctl &>/dev/null; then
  warn "systemctl is not available."
  warn "The SSH & Web Terminal add-on has Protection Mode ENABLED."
  warn "Service registration steps will be skipped."
  warn ""
  warn "To fix: Home Assistant > Settings > Add-ons > SSH & Web Terminal"
  warn "        Toggle OFF 'Protection Mode' > Save > Restart add-on"
  warn "Then re-run this script."
  echo ""
  SYSTEMD_AVAILABLE=0
else
  ok "systemctl found — systemd service registration will proceed."
  SYSTEMD_AVAILABLE=1
fi

# -----------------------------------------------------------------------------
# Configuration
# All paths are under /config/ — the only reliably persistent directory on
# Home Assistant OS. The OS partition itself is read-only and wiped on updates.
# -----------------------------------------------------------------------------
REPO_URL="https://github.com/CC90210/Aura-Home-Agent.git"
AURA_DIR="/config/aura"
VENV_DIR="${AURA_DIR}/.venv"
DATA_DIR="${AURA_DIR}/data"
MEMORY_DIR="${AURA_DIR}/memory"
ENV_EXAMPLE="${AURA_DIR}/.env.example"
ENV_FILE="${AURA_DIR}/.env"

echo ""
info "Install path : ${AURA_DIR}"
info "Venv path    : ${VENV_DIR}"
info "Repo URL     : ${REPO_URL}"
echo ""

# =============================================================================
# Step 1 — Check and install prerequisites
# Alpine's package manager is apk, NOT apt-get.
# Package name mappings used here (Alpine differs from Debian):
#   py3-pip       — pip for Python 3        (NOT python3-pip)
#   portaudio-dev — C headers for PyAudio   (NOT portaudio19-dev)
#   python3-dev   — Python C headers        (same name on Alpine)
#   musl-dev      — Alpine's libc headers   (needed for C extension builds)
#   openblas-dev  — OpenBLAS for NumPy      (NOT libopenblas-dev)
# =============================================================================
step "[1/9] Checking and installing prerequisites..."

info "Updating Alpine package index..."
apk update --quiet

PACKAGES_BASE=(python3 py3-pip portaudio-dev gcc python3-dev musl-dev alsa-utils git)

for pkg in "${PACKAGES_BASE[@]}"; do
  if apk info --installed "${pkg}" &>/dev/null; then
    ok "  ${pkg} already installed"
  else
    info "  Installing ${pkg}..."
    apk add --no-cache --quiet "${pkg}"
    ok "  ${pkg} installed"
  fi
done

# =============================================================================
# Step 2 — Clone the repo (idempotent: skip if already present)
# =============================================================================
step "[2/9] Cloning AURA repo..."

if [[ -d "${AURA_DIR}/.git" ]]; then
  warn "Repo already exists at ${AURA_DIR} — skipping clone."
  warn "To re-clone from scratch: rm -rf ${AURA_DIR} and re-run this script."
else
  info "Cloning ${REPO_URL} into ${AURA_DIR}..."
  git clone "${REPO_URL}" "${AURA_DIR}"
  ok "Repo cloned to ${AURA_DIR}"
fi

# -----------------------------------------------------------------------------
# Configure git so future `git pull` merges cleanly (no rebase divergence)
# -----------------------------------------------------------------------------
cd "${AURA_DIR}"
git config pull.rebase false
ok "git pull.rebase set to false (merge strategy)"

# =============================================================================
# Step 3 — Create Python virtual environment (idempotent)
# python3 -m venv is included in the python3 package on Alpine when py3-pip
# is also present. No separate python3-venv package needed.
# =============================================================================
step "[3/9] Setting up Python virtual environment..."

if [[ -d "${VENV_DIR}" && -x "${VENV_DIR}/bin/python3" ]]; then
  ok "Venv already exists at ${VENV_DIR} — skipping creation."
else
  info "Creating venv at ${VENV_DIR}..."
  python3 -m venv "${VENV_DIR}"
  ok "Venv created."
fi

# Upgrade pip inside the venv once
info "Upgrading pip inside venv..."
"${VENV_DIR}/bin/pip" install --quiet --upgrade pip
ok "pip upgraded."

# =============================================================================
# Step 4 — Install Python requirements: clap-trigger
# PyAudio compiles a C extension and links against portaudio — that is why
# gcc, python3-dev, musl-dev, and portaudio-dev were installed in step 1.
# =============================================================================
step "[4/9] Installing clap-trigger Python dependencies..."

CLAP_REQ="${AURA_DIR}/clap-trigger/requirements.txt"
if [[ ! -f "${CLAP_REQ}" ]]; then
  err "requirements.txt not found at ${CLAP_REQ}"
  err "The clone may have been incomplete. Try: rm -rf ${AURA_DIR} and re-run."
  exit 1
fi

"${VENV_DIR}/bin/pip" install --quiet -r "${CLAP_REQ}"
ok "clap-trigger dependencies installed."

# =============================================================================
# Step 5 — Install Python requirements: voice-agent
# Requires additional system packages (ffmpeg, openblas-dev, libsndfile).
# Skip with SKIP_VOICE_AGENT=1 if voice pipeline is not yet needed.
# =============================================================================
step "[5/9] Installing voice-agent Python dependencies..."

if [[ "${SKIP_VOICE_AGENT:-0}" == "1" ]]; then
  warn "SKIP_VOICE_AGENT=1 — skipping voice agent installation."
else
  info "Installing voice agent system packages (ffmpeg, openblas-dev, libsndfile)..."
  apk add --no-cache --quiet openblas-dev ffmpeg libsndfile
  ok "Voice agent system packages installed."

  VOICE_REQ="${AURA_DIR}/voice-agent/requirements.txt"
  if [[ ! -f "${VOICE_REQ}" ]]; then
    warn "voice-agent/requirements.txt not found at ${VOICE_REQ} — skipping."
  else
    "${VENV_DIR}/bin/pip" install --quiet -r "${VOICE_REQ}"
    ok "voice-agent dependencies installed."
  fi
fi

# =============================================================================
# Step 6 — Install Python requirements: learning
# =============================================================================
step "[6/9] Installing learning module Python dependencies..."

LEARNING_REQ="${AURA_DIR}/learning/requirements.txt"
if [[ ! -f "${LEARNING_REQ}" ]]; then
  warn "learning/requirements.txt not found at ${LEARNING_REQ} — skipping."
else
  "${VENV_DIR}/bin/pip" install --quiet -r "${LEARNING_REQ}"
  ok "Learning module dependencies installed."
fi

# =============================================================================
# Step 7 — Copy .env.example → .env (idempotent: never overwrites an existing .env)
# The operator MUST fill in secrets before starting services.
# =============================================================================
step "[7/9] Preparing .env file..."

if [[ -f "${ENV_FILE}" ]]; then
  ok ".env already exists at ${ENV_FILE} — not overwriting."
  warn "Verify that all required secrets are filled in."
else
  if [[ -f "${ENV_EXAMPLE}" ]]; then
    cp "${ENV_EXAMPLE}" "${ENV_FILE}"
    ok ".env created from .env.example at ${ENV_FILE}"
    warn "ACTION REQUIRED: Open ${ENV_FILE} and fill in your API keys and tokens."
    warn "Services will NOT start correctly until secrets are populated."
  else
    warn ".env.example not found at ${ENV_EXAMPLE}"
    warn "Create ${ENV_FILE} manually with your secrets before starting services."
  fi
fi

# =============================================================================
# Step 8 — Register systemd services (idempotent)
# Copies service unit files, reloads the daemon, and enables both services for
# auto-start on boot. Does NOT start them — the operator must populate .env first.
# Requires Protection Mode OFF on the SSH & Web Terminal add-on.
# =============================================================================
step "[8/9] Registering systemd services..."

CLAP_SERVICE_SRC="${AURA_DIR}/clap-trigger/clap_service.service"
CLAP_SERVICE_DEST="/etc/systemd/system/clap_service.service"
VOICE_SERVICE_SRC="${AURA_DIR}/voice-agent/aura_voice.service"
VOICE_SERVICE_DEST="/etc/systemd/system/aura_voice.service"

if [[ "${SYSTEMD_AVAILABLE}" -eq 0 ]]; then
  warn "systemctl not available — skipping service registration."
  warn "Disable Protection Mode on the SSH add-on and re-run to register services."
else
  # clap_service
  if [[ -f "${CLAP_SERVICE_SRC}" ]]; then
    cp "${CLAP_SERVICE_SRC}" "${CLAP_SERVICE_DEST}"
    chmod 644 "${CLAP_SERVICE_DEST}"
    ok "clap_service.service copied to ${CLAP_SERVICE_DEST}"
  else
    warn "clap_service.service not found at ${CLAP_SERVICE_SRC} — skipping."
  fi

  # aura_voice (only if not skipped)
  if [[ "${SKIP_VOICE_AGENT:-0}" == "1" ]]; then
    warn "SKIP_VOICE_AGENT=1 — skipping aura_voice.service registration."
  elif [[ -f "${VOICE_SERVICE_SRC}" ]]; then
    cp "${VOICE_SERVICE_SRC}" "${VOICE_SERVICE_DEST}"
    chmod 644 "${VOICE_SERVICE_DEST}"
    ok "aura_voice.service copied to ${VOICE_SERVICE_DEST}"
  else
    warn "aura_voice.service not found at ${VOICE_SERVICE_SRC} — skipping."
  fi

  # Reload daemon to pick up both unit files in one pass
  systemctl daemon-reload
  ok "systemd daemon reloaded."

  # Enable for auto-start on boot (but do NOT start yet)
  if [[ -f "${CLAP_SERVICE_DEST}" ]]; then
    systemctl enable clap_service
    ok "clap_service enabled (auto-starts on boot)."
  fi

  if [[ "${SKIP_VOICE_AGENT:-0}" != "1" && -f "${VOICE_SERVICE_DEST}" ]]; then
    systemctl enable aura_voice
    ok "aura_voice enabled (auto-starts on boot)."
  fi
fi

# =============================================================================
# Step 9 — Create data directories
# /config/aura/data  — runtime data (SQLite DBs, learned patterns, logs)
# /config/aura/memory — AURA memory files (personality overrides, learned speech)
# Both directories are checked into .gitignore so git pull never clobbers them.
# =============================================================================
step "[9/9] Creating data directories..."

for dir in "${DATA_DIR}" "${MEMORY_DIR}"; do
  if [[ -d "${dir}" ]]; then
    ok "  ${dir} already exists."
  else
    mkdir -p "${dir}"
    ok "  Created ${dir}"
  fi
done

# =============================================================================
# Done — print next steps
# =============================================================================
echo ""
banner "=================================================="
banner "  AURA First-Time Setup Complete!"
banner "=================================================="
echo ""
printf "${_BOLD}Next steps:${_RESET}\n"
echo ""
printf "  ${_YELLOW}1. Fill in your secrets in .env:${_RESET}\n"
echo "       nano ${ENV_FILE}"
echo "     Required keys: HA_URL, HA_TOKEN, ANTHROPIC_API_KEY,"
echo "                    ELEVENLABS_API_KEY, GOVEE_API_KEY, SPOTIFY_CLIENT_ID"
echo ""
printf "  ${_YELLOW}2. Verify the install:${_RESET}\n"
echo "       bash ${AURA_DIR}/scripts/setup/verify_install.sh"
echo ""
printf "  ${_YELLOW}3. Start the services:${_RESET}\n"
echo "       systemctl start aura_voice clap_service"
echo ""
printf "  ${_YELLOW}4. Watch live logs:${_RESET}\n"
echo "       journalctl -u aura_voice -f"
echo "       journalctl -u clap_service -f"
echo ""
printf "  ${_YELLOW}5. Test a webhook manually:${_RESET}\n"
echo "       curl -X POST http://homeassistant.local:8123/api/webhook/aura_double_clap"
echo ""
printf "${_BOLD}For all future updates (run from your desktop):${_RESET}\n"
echo ""
echo "       bash scripts/deploy/update_configs.sh --restart"
echo ""
printf "${_BOLD}To pull the latest AURA code on the Pi directly:${_RESET}\n"
echo ""
echo "       cd ${AURA_DIR} && git pull"
echo ""
if [[ "${SYSTEMD_AVAILABLE}" -eq 0 ]]; then
  printf "${_RED}REMINDER:${_RESET} Services were NOT registered because Protection Mode is ON.\n"
  echo "  Disable it and re-run this script to complete service registration."
  echo ""
fi
