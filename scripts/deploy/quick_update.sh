#!/usr/bin/env bash
# =============================================================================
# AURA by OASIS — quick_update.sh
# One-command deploy: pull latest code from GitHub to the Raspberry Pi.
#
# What it does:
#   1. Loads PI_HOST / PI_USER from .env (project root)
#   2. Tests SSH connectivity
#   3. SSHes into the Pi and runs: git pull origin main
#   4. Optionally reinstalls pip packages from requirements.txt (--deps)
#   5. Optionally restarts systemd services (aura_voice, clap_service) (--restart)
#   6. Runs a health check: HA API ping + systemd service status
#   7. Prints elapsed time
#
# Usage:
#   bash scripts/deploy/quick_update.sh              # git pull only
#   bash scripts/deploy/quick_update.sh --deps       # pull + pip install
#   bash scripts/deploy/quick_update.sh --restart    # pull + restart services
#   bash scripts/deploy/quick_update.sh --all        # pull + deps + restart
#   bash scripts/deploy/quick_update.sh --dry-run    # show what would happen, do nothing
#
# Requirements on the Pi:
#   - Repo cloned at /config/aura/   (git remote: CC90210/Aura-Home-Agent)
#   - Python venv at /config/aura/.venv/
#   - Systemd services: aura_voice.service, clap_service.service
#   - SSH key-based auth already set up (ssh-copy-id root@homeassistant.local)
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Resolve paths
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Record start time (seconds since epoch)
START_TS=$(date +%s)

# -----------------------------------------------------------------------------
# Color helpers
# -----------------------------------------------------------------------------
# Check whether the terminal supports colors
if [[ -t 1 ]] && command -v tput &>/dev/null && tput colors &>/dev/null && [[ "$(tput colors)" -ge 8 ]]; then
    C_RESET="\033[0m"
    C_BOLD="\033[1m"
    C_GREEN="\033[0;32m"
    C_YELLOW="\033[0;33m"
    C_CYAN="\033[0;36m"
    C_RED="\033[0;31m"
    C_DIM="\033[2m"
else
    C_RESET="" C_BOLD="" C_GREEN="" C_YELLOW="" C_CYAN="" C_RED="" C_DIM=""
fi

log_step()  { echo -e "${C_BOLD}${C_CYAN}[${1}]${C_RESET} ${2}"; }
log_ok()    { echo -e "      ${C_GREEN}OK${C_RESET}  ${1}"; }
log_warn()  { echo -e "      ${C_YELLOW}WARN${C_RESET} ${1}"; }
log_err()   { echo -e "      ${C_RED}ERR${C_RESET}  ${1}" >&2; }
log_info()  { echo -e "      ${C_DIM}${1}${C_RESET}"; }
log_dry()   { echo -e "      ${C_YELLOW}DRY-RUN${C_RESET} would run: ${C_DIM}${1}${C_RESET}"; }

# -----------------------------------------------------------------------------
# Usage / help
# -----------------------------------------------------------------------------
usage() {
    echo ""
    echo -e "${C_BOLD}AURA by OASIS — quick_update.sh${C_RESET}"
    echo "Pull the latest code from GitHub to the Raspberry Pi."
    echo ""
    echo -e "${C_BOLD}Usage:${C_RESET}"
    echo "  bash scripts/deploy/quick_update.sh [flags]"
    echo ""
    echo -e "${C_BOLD}Flags:${C_RESET}"
    echo "  --deps      Reinstall Python packages from requirements.txt"
    echo "  --restart   Restart systemd services (aura_voice, clap_service)"
    echo "  --all       Equivalent to --deps --restart"
    echo "  --dry-run   Show what would happen without executing anything"
    echo "  --help      Show this help and exit"
    echo ""
    echo -e "${C_BOLD}Environment (.env):${C_RESET}"
    echo "  PI_HOST     Hostname or IP of the Pi  (default: homeassistant.local)"
    echo "  PI_USER     SSH user on the Pi         (default: root)"
    echo "  HA_URL      Home Assistant URL          (default: http://\$PI_HOST:8123)"
    echo "  HA_TOKEN    Long-lived HA access token  (required for health check)"
    echo ""
    echo -e "${C_BOLD}Remote paths (fixed):${C_RESET}"
    echo "  Repo  : /config/aura/"
    echo "  Venv  : /config/aura/.venv/"
    echo ""
}

# -----------------------------------------------------------------------------
# Parse flags
# -----------------------------------------------------------------------------
INSTALL_DEPS=false
RESTART_SERVICES=false
DRY_RUN=false

for arg in "$@"; do
    case "${arg}" in
        --deps)    INSTALL_DEPS=true ;;
        --restart) RESTART_SERVICES=true ;;
        --all)     INSTALL_DEPS=true; RESTART_SERVICES=true ;;
        --dry-run) DRY_RUN=true ;;
        --help|-h) usage; exit 0 ;;
        *)
            echo -e "${C_RED}ERROR:${C_RESET} Unknown flag: ${arg}"
            usage
            exit 1
            ;;
    esac
done

# -----------------------------------------------------------------------------
# Load .env
# -----------------------------------------------------------------------------
if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "${PROJECT_ROOT}/.env"
    set +a
fi

PI_HOST="${PI_HOST:-homeassistant.local}"
PI_USER="${PI_USER:-root}"
HA_URL="${HA_URL:-http://${PI_HOST}:8123}"
HA_TOKEN="${HA_TOKEN:-}"

REMOTE_REPO_DIR="/config/aura"
REMOTE_VENV="${REMOTE_REPO_DIR}/.venv"

# Services to manage, in restart order
SERVICES=("clap_service" "aura_voice")

# -----------------------------------------------------------------------------
# Banner
# -----------------------------------------------------------------------------
echo ""
echo -e "${C_BOLD}${C_CYAN}=================================================${C_RESET}"
echo -e "${C_BOLD}${C_CYAN}  AURA by OASIS — Quick Update${C_RESET}"
echo -e "${C_BOLD}${C_CYAN}=================================================${C_RESET}"
echo -e "  Target   : ${PI_USER}@${PI_HOST}"
echo -e "  Repo     : ${REMOTE_REPO_DIR}"
echo -e "  Deps     : ${INSTALL_DEPS}"
echo -e "  Restart  : ${RESTART_SERVICES}"
if [[ "${DRY_RUN}" == "true" ]]; then
echo -e "  ${C_YELLOW}Mode     : DRY RUN — nothing will be changed${C_RESET}"
fi
echo -e "${C_BOLD}${C_CYAN}=================================================${C_RESET}"
echo ""

# -----------------------------------------------------------------------------
# Dry-run helper — wraps ssh and local commands
# -----------------------------------------------------------------------------
# When --dry-run is active we print what we would do instead of doing it.
ssh_run() {
    # Usage: ssh_run "<description>" "<remote commands>"
    local desc="$1"
    local cmds="$2"
    if [[ "${DRY_RUN}" == "true" ]]; then
        log_dry "ssh ${PI_USER}@${PI_HOST} << '...'"
        while IFS= read -r line; do
            [[ -n "${line// }" ]] && log_dry "  ${line}"
        done <<< "${cmds}"
    else
        ssh -o ConnectTimeout=15 -o BatchMode=yes \
            "${PI_USER}@${PI_HOST}" "${cmds}"
    fi
}

# -----------------------------------------------------------------------------
# Step 1 — SSH connectivity check
# -----------------------------------------------------------------------------
TOTAL_STEPS=4
[[ "${INSTALL_DEPS}" == "true" ]] && (( TOTAL_STEPS++ )) || true
[[ "${RESTART_SERVICES}" == "true" ]] && (( TOTAL_STEPS++ )) || true
CURRENT_STEP=0

(( CURRENT_STEP++ )) || true
log_step "${CURRENT_STEP}/${TOTAL_STEPS}" "Testing SSH connection to ${PI_HOST}..."

if [[ "${DRY_RUN}" == "true" ]]; then
    log_dry "ssh -o ConnectTimeout=10 -o BatchMode=yes ${PI_USER}@${PI_HOST} 'echo SSH OK'"
elif ! ssh -o ConnectTimeout=10 -o BatchMode=yes \
        "${PI_USER}@${PI_HOST}" "echo 'SSH OK'" &>/dev/null; then
    log_err "Cannot connect to ${PI_USER}@${PI_HOST} via SSH."
    log_info "Make sure:"
    log_info "  - The Pi is powered on and connected to the network"
    log_info "  - SSH keys are configured: ssh-copy-id ${PI_USER}@${PI_HOST}"
    log_info "  - PI_HOST and PI_USER in .env are correct"
    exit 1
fi
log_ok "SSH connection established."
echo ""

# -----------------------------------------------------------------------------
# Step 2 — git pull on the Pi
# -----------------------------------------------------------------------------
(( CURRENT_STEP++ )) || true
log_step "${CURRENT_STEP}/${TOTAL_STEPS}" "Pulling latest code from GitHub..."

GIT_PULL_CMD="
set -e
cd ${REMOTE_REPO_DIR}
echo '--- git status (before) ---'
git status --short
echo '--- git pull ---'
git pull origin main
echo '--- done ---'
"

if [[ "${DRY_RUN}" == "true" ]]; then
    log_dry "ssh ${PI_USER}@${PI_HOST}"
    log_dry "  cd ${REMOTE_REPO_DIR}"
    log_dry "  git pull origin main"
else
    PULL_OUTPUT=$(ssh -o ConnectTimeout=15 -o BatchMode=yes \
        "${PI_USER}@${PI_HOST}" "${GIT_PULL_CMD}" 2>&1) || {
        log_err "git pull failed. Raw output:"
        echo "${PULL_OUTPUT}" | sed 's/^/          /' >&2
        exit 1
    }

    # Surface key lines from git output
    while IFS= read -r line; do
        case "${line}" in
            "Already up to date.")  log_ok "Already up to date — no changes." ;;
            ---*)                   : ;;  # separator lines, skip
            "")                     : ;;
            *)                      log_info "${line}" ;;
        esac
    done <<< "${PULL_OUTPUT}"
fi
log_ok "Code pull complete."
echo ""

# -----------------------------------------------------------------------------
# Step 3 (optional) — pip install requirements
# -----------------------------------------------------------------------------
if [[ "${INSTALL_DEPS}" == "true" ]]; then
    (( CURRENT_STEP++ )) || true
    log_step "${CURRENT_STEP}/${TOTAL_STEPS}" "Installing Python dependencies..."

    # We install from every requirements.txt found under the repo directory.
    # Ordering: clap-trigger, learning, voice-agent (dependency order matters).
    REQUIREMENTS_FILES=(
        "${REMOTE_REPO_DIR}/clap-trigger/requirements.txt"
        "${REMOTE_REPO_DIR}/learning/requirements.txt"
        "${REMOTE_REPO_DIR}/voice-agent/requirements.txt"
    )

    PIP_CMDS="set -e; source ${REMOTE_VENV}/bin/activate"
    for req in "${REQUIREMENTS_FILES[@]}"; do
        PIP_CMDS+="
if [ -f ${req} ]; then
    echo '--- pip install: ${req} ---'
    pip install --quiet -r ${req}
    echo 'OK: ${req}'
else
    echo 'SKIP (not found): ${req}'
fi"
    done

    if [[ "${DRY_RUN}" == "true" ]]; then
        log_dry "ssh ${PI_USER}@${PI_HOST}"
        log_dry "  source ${REMOTE_VENV}/bin/activate"
        for req in "${REQUIREMENTS_FILES[@]}"; do
            log_dry "  pip install -r ${req}  (if exists)"
        done
    else
        PIP_OUTPUT=$(ssh -o ConnectTimeout=30 -o BatchMode=yes \
            -o ServerAliveInterval=30 \
            "${PI_USER}@${PI_HOST}" "${PIP_CMDS}" 2>&1) || {
            log_err "pip install failed. Raw output:"
            echo "${PIP_OUTPUT}" | sed 's/^/          /' >&2
            exit 1
        }
        while IFS= read -r line; do
            case "${line}" in
                OK:*)      log_ok "${line#OK: }" ;;
                SKIP*)     log_warn "${line}" ;;
                ---)       : ;;
                "")        : ;;
                *)         log_info "${line}" ;;
            esac
        done <<< "${PIP_OUTPUT}"
    fi
    log_ok "Dependencies installed."
    echo ""
fi

# -----------------------------------------------------------------------------
# Step 4 (optional) — restart systemd services
# -----------------------------------------------------------------------------
if [[ "${RESTART_SERVICES}" == "true" ]]; then
    (( CURRENT_STEP++ )) || true
    log_step "${CURRENT_STEP}/${TOTAL_STEPS}" "Restarting systemd services..."

    for svc in "${SERVICES[@]}"; do
        if [[ "${DRY_RUN}" == "true" ]]; then
            log_dry "systemctl restart ${svc}.service"
        else
            RESTART_OUTPUT=$(ssh -o ConnectTimeout=15 -o BatchMode=yes \
                "${PI_USER}@${PI_HOST}" "
                    if systemctl list-unit-files --type=service | grep -q '^${svc}.service'; then
                        systemctl restart ${svc}.service && echo 'RESTARTED:${svc}' || echo 'FAILED:${svc}'
                    else
                        echo 'NOT_FOUND:${svc}'
                    fi
                " 2>&1) || true

            case "${RESTART_OUTPUT}" in
                RESTARTED:*)  log_ok "${svc}.service restarted." ;;
                NOT_FOUND:*)  log_warn "${svc}.service not found on Pi — skipping." ;;
                FAILED:*)     log_err "${svc}.service restart failed." ;;
                *)            log_info "${svc}: ${RESTART_OUTPUT}" ;;
            esac
        fi
    done
    log_ok "Service restart complete."
    echo ""
fi

# -----------------------------------------------------------------------------
# Step N-1 — Health check
# -----------------------------------------------------------------------------
(( CURRENT_STEP++ )) || true
log_step "${CURRENT_STEP}/${TOTAL_STEPS}" "Running health check..."

# 1. Ping the Home Assistant API
if [[ "${DRY_RUN}" == "true" ]]; then
    log_dry "curl -s -o /dev/null -w '%{http_code}' ${HA_URL}/api/"
elif [[ -z "${HA_TOKEN}" ]]; then
    log_warn "HA_TOKEN not set — skipping Home Assistant API ping."
    log_info "Set HA_TOKEN in .env to enable the API health check."
else
    HTTP_CODE=$(curl --silent --output /dev/null --max-time 10 \
        -w "%{http_code}" \
        -H "Authorization: Bearer ${HA_TOKEN}" \
        -H "Content-Type: application/json" \
        "${HA_URL}/api/" 2>/dev/null) || HTTP_CODE="000"

    case "${HTTP_CODE}" in
        200|201) log_ok "Home Assistant API responded: HTTP ${HTTP_CODE}" ;;
        401)     log_warn "HA API returned 401 — HA_TOKEN may be invalid or expired." ;;
        000)     log_warn "HA API unreachable (timeout or connection refused) — HA may still be starting." ;;
        *)       log_warn "HA API returned unexpected status: HTTP ${HTTP_CODE}" ;;
    esac
fi

# 2. Check systemd service status on the Pi
if [[ "${DRY_RUN}" == "true" ]]; then
    for svc in "${SERVICES[@]}"; do
        log_dry "systemctl is-active ${svc}.service"
    done
else
    for svc in "${SERVICES[@]}"; do
        SVC_STATUS=$(ssh -o ConnectTimeout=10 -o BatchMode=yes \
            "${PI_USER}@${PI_HOST}" "
                if systemctl list-unit-files --type=service | grep -q '^${svc}.service'; then
                    systemctl is-active ${svc}.service 2>/dev/null || true
                else
                    echo 'not-installed'
                fi
            " 2>/dev/null) || SVC_STATUS="unknown"

        case "${SVC_STATUS}" in
            active)        log_ok "${svc}.service is running." ;;
            inactive)      log_warn "${svc}.service is installed but not running." ;;
            not-installed) log_warn "${svc}.service is not installed on this Pi." ;;
            failed)        log_err "${svc}.service is in a FAILED state — check: journalctl -u ${svc} -n 50" ;;
            *)             log_warn "${svc}.service status: ${SVC_STATUS}" ;;
        esac
    done
fi
echo ""

# -----------------------------------------------------------------------------
# Step N — Summary
# -----------------------------------------------------------------------------
(( CURRENT_STEP++ )) || true
END_TS=$(date +%s)
ELAPSED=$(( END_TS - START_TS ))
ELAPSED_FMT=$(printf "%dm %02ds" $(( ELAPSED / 60 )) $(( ELAPSED % 60 )))

echo -e "${C_BOLD}${C_CYAN}=================================================${C_RESET}"
if [[ "${DRY_RUN}" == "true" ]]; then
echo -e "${C_BOLD}${C_YELLOW}  Dry run complete — no changes were made.${C_RESET}"
else
echo -e "${C_BOLD}${C_GREEN}  Update complete!${C_RESET}"
fi
echo -e "${C_BOLD}${C_CYAN}=================================================${C_RESET}"
echo -e "  Target   : ${PI_USER}@${PI_HOST}"
echo -e "  Deps     : ${INSTALL_DEPS}"
echo -e "  Restart  : ${RESTART_SERVICES}"
echo -e "  Elapsed  : ${ELAPSED_FMT}"
echo -e "${C_BOLD}${C_CYAN}=================================================${C_RESET}"
echo ""

if [[ "${DRY_RUN}" != "true" ]] && [[ "${RESTART_SERVICES}" != "true" ]]; then
    echo -e "${C_DIM}Tip: run with --restart to bounce aura_voice and clap_service${C_RESET}"
    echo -e "${C_DIM}Tip: run with --all to reinstall deps and restart services${C_RESET}"
    echo ""
fi
