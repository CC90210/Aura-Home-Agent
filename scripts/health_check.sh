#!/usr/bin/env bash
# =============================================================================
# AURA by OASIS — health_check.sh
# Run FROM the desktop to verify the Pi and all AURA services are healthy.
#
# Checks:
#   1.  SSH connectivity to Pi
#   2.  Home Assistant API responds (HTTP 200)
#   3.  systemd service: aura_voice
#   4.  systemd service: clap_service
#   5.  Disk usage on Pi (warn > 80%, fail > 95%)
#   6.  CPU temperature on Pi
#   7.  Python venv exists and is valid
#   8.  .env present at /config/aura/.env
#   9.  Voice agent health endpoint (port 5123)
#
# Exit codes:
#   0  All critical checks pass (warnings allowed).
#   1  One or more critical checks failed.
#
# Usage:
#   bash scripts/health_check.sh
# =============================================================================

set -uo pipefail

# -----------------------------------------------------------------------------
# Resolve repo root and load .env
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ -f "$PROJECT_ROOT/.env" ]]; then
    set -a; source "$PROJECT_ROOT/.env"; set +a
fi

# -----------------------------------------------------------------------------
# Configuration — all overridable via .env
# -----------------------------------------------------------------------------
PI_HOST="${PI_HOST:-homeassistant.local}"
PI_USER="${PI_USER:-root}"
HA_TOKEN="${HA_TOKEN:-}"
HA_URL="${HA_URL:-http://${PI_HOST}:8123}"
VOICE_AGENT_HEALTH_URL="http://${PI_HOST}:5123/health"
DISK_WARN_THRESHOLD=80
DISK_FAIL_THRESHOLD=95
CPU_WARN_THRESHOLD=75   # degrees Celsius
SSH_TIMEOUT=10
CURL_TIMEOUT=10

# -----------------------------------------------------------------------------
# Coloured output — degrade gracefully when stdout is not a terminal
# -----------------------------------------------------------------------------
if [[ -t 1 ]]; then
    COL_PASS="\033[0;32m"    # green
    COL_WARN="\033[0;33m"    # yellow
    COL_FAIL="\033[0;31m"    # red
    COL_HEAD="\033[1;36m"    # bold cyan
    COL_DIM="\033[0;90m"     # grey
    COL_RESET="\033[0m"
else
    COL_PASS=""
    COL_WARN=""
    COL_FAIL=""
    COL_HEAD=""
    COL_DIM=""
    COL_RESET=""
fi

# Counters
PASS=0
WARN=0
FAIL=0
# Track whether any *critical* check has failed.
# Warnings never set CRITICAL_FAIL — only explicit fail() calls do.
CRITICAL_FAIL=0

pass() {
    echo -e "  ${COL_PASS}[PASS]${COL_RESET} $1"
    PASS=$(( PASS + 1 ))
}

warn() {
    echo -e "  ${COL_WARN}[WARN]${COL_RESET} $1"
    WARN=$(( WARN + 1 ))
}

fail() {
    echo -e "  ${COL_FAIL}[FAIL]${COL_RESET} $1"
    FAIL=$(( FAIL + 1 ))
    CRITICAL_FAIL=1
}

info() {
    echo -e "  ${COL_DIM}       $1${COL_RESET}"
}

# Helper: run a command on the Pi via SSH (non-interactive, strict timeout).
# Returns the command's stdout; returns non-zero exit on SSH failure.
ssh_run() {
    ssh -o ConnectTimeout="${SSH_TIMEOUT}" \
        -o StrictHostKeyChecking=no \
        -o BatchMode=yes \
        -o LogLevel=ERROR \
        "${PI_USER}@${PI_HOST}" "$@" 2>/dev/null
}

# -----------------------------------------------------------------------------
# Header
# -----------------------------------------------------------------------------
echo ""
echo -e "${COL_HEAD}=============================================="
echo    "  AURA by OASIS -- Health Check"
echo -e "==============================================${COL_RESET}"
echo -e "  Pi host  : ${PI_HOST}"
echo -e "  Pi user  : ${PI_USER}"
echo -e "  HA URL   : ${HA_URL}"
echo -e "  Date     : $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# =============================================================================
# CHECK 1: SSH connectivity
# =============================================================================
echo "[ 1/9  SSH connectivity ]"

if ssh_run "echo ok" &>/dev/null; then
    pass "SSH connection to ${PI_USER}@${PI_HOST} succeeded"
    SSH_OK=1
else
    fail "Cannot SSH into ${PI_USER}@${PI_HOST}"
    info "Ensure the Pi is powered on, connected to the same network, and SSH"
    info "is enabled. Test manually: ssh ${PI_USER}@${PI_HOST}"
    SSH_OK=0
fi
echo ""

# =============================================================================
# CHECK 2: Home Assistant API
# =============================================================================
echo "[ 2/9  Home Assistant API ]"

if ! command -v curl &>/dev/null; then
    warn "curl not installed — cannot check Home Assistant API"
else
    if [[ -z "${HA_TOKEN}" || "${HA_TOKEN}" == "your_"* ]]; then
        warn "HA_TOKEN is not set in .env — authenticating without token"
        HA_HTTP_CODE=$(curl --silent --max-time "${CURL_TIMEOUT}" \
            --write-out "%{http_code}" --output /dev/null \
            "${HA_URL}/api/" 2>/dev/null || echo "000")
    else
        HA_HTTP_CODE=$(curl --silent --max-time "${CURL_TIMEOUT}" \
            --write-out "%{http_code}" --output /dev/null \
            -H "Authorization: Bearer ${HA_TOKEN}" \
            "${HA_URL}/api/" 2>/dev/null || echo "000")
    fi

    case "${HA_HTTP_CODE}" in
        200)
            pass "Home Assistant API responded HTTP 200 at ${HA_URL}/api/"
            ;;
        401)
            warn "Home Assistant API responded HTTP 401 — HA_TOKEN may be invalid or expired"
            info "Rotate token: HA → Profile → Long-Lived Access Tokens"
            ;;
        000)
            fail "Home Assistant did not respond (connection refused or timeout)"
            info "Is Home Assistant running? Check: ${HA_URL}"
            ;;
        *)
            warn "Home Assistant returned unexpected HTTP ${HA_HTTP_CODE}"
            info "URL: ${HA_URL}/api/"
            ;;
    esac
fi
echo ""

# =============================================================================
# CHECK 3: systemd service — aura_voice
# =============================================================================
echo "[ 3/9  Service: aura_voice ]"

if [[ "${SSH_OK}" -eq 0 ]]; then
    warn "SSH unavailable — skipping service check for aura_voice"
else
    SVC_STATE=$(ssh_run "systemctl is-active aura_voice 2>/dev/null" || echo "unknown")
    case "${SVC_STATE}" in
        active)
            pass "aura_voice service is active (running)"
            ;;
        inactive)
            warn "aura_voice service is inactive (stopped but not failed)"
            info "Start with: systemctl start aura_voice"
            ;;
        failed)
            fail "aura_voice service is in a failed state"
            info "Inspect with: journalctl -u aura_voice -n 50"
            info "Restart with: systemctl restart aura_voice"
            ;;
        activating)
            warn "aura_voice service is still starting up"
            ;;
        *)
            warn "aura_voice service state is '${SVC_STATE}' (may not be installed yet)"
            info "Deploy with: bash scripts/deploy/deploy_services.sh"
            ;;
    esac
fi
echo ""

# =============================================================================
# CHECK 4: systemd service — clap_service
# =============================================================================
echo "[ 4/9  Service: clap_service ]"

if [[ "${SSH_OK}" -eq 0 ]]; then
    warn "SSH unavailable — skipping service check for clap_service"
else
    SVC_STATE=$(ssh_run "systemctl is-active clap_service 2>/dev/null" || echo "unknown")
    case "${SVC_STATE}" in
        active)
            pass "clap_service is active (running)"
            ;;
        inactive)
            warn "clap_service is inactive (stopped but not failed)"
            info "Start with: systemctl start clap_service"
            ;;
        failed)
            fail "clap_service is in a failed state"
            info "Inspect with: journalctl -u clap_service -n 50"
            info "Restart with: systemctl restart clap_service"
            ;;
        activating)
            warn "clap_service is still starting up"
            ;;
        *)
            warn "clap_service state is '${SVC_STATE}' (may not be installed yet)"
            info "Deploy with: bash scripts/deploy/deploy_services.sh"
            ;;
    esac
fi
echo ""

# =============================================================================
# CHECK 5: Disk usage on Pi
# =============================================================================
echo "[ 5/9  Disk usage (Pi) ]"

if [[ "${SSH_OK}" -eq 0 ]]; then
    warn "SSH unavailable — skipping disk usage check"
else
    # df output: Filesystem 1K-blocks Used Available Use% Mounted
    DISK_LINE=$(ssh_run "df -h / 2>/dev/null | tail -1" || echo "")
    if [[ -z "${DISK_LINE}" ]]; then
        warn "Could not retrieve disk usage from Pi"
    else
        DISK_PCT=$(echo "${DISK_LINE}" | awk '{print $5}' | tr -d '%')
        DISK_USED=$(echo "${DISK_LINE}" | awk '{print $3}')
        DISK_AVAIL=$(echo "${DISK_LINE}" | awk '{print $4}')
        DISK_TOTAL=$(echo "${DISK_LINE}" | awk '{print $2}')

        if [[ "${DISK_PCT}" =~ ^[0-9]+$ ]]; then
            if [[ "${DISK_PCT}" -ge "${DISK_FAIL_THRESHOLD}" ]]; then
                fail "Disk usage is critically high: ${DISK_PCT}% (${DISK_USED} / ${DISK_TOTAL} used, ${DISK_AVAIL} free)"
                info "Free space urgently: remove old HA backups, Whisper models, or log files"
            elif [[ "${DISK_PCT}" -ge "${DISK_WARN_THRESHOLD}" ]]; then
                warn "Disk usage is elevated: ${DISK_PCT}% (${DISK_USED} / ${DISK_TOTAL} used, ${DISK_AVAIL} free)"
                info "Consider removing old HA backups: HA → Settings → Backups"
            else
                pass "Disk usage is healthy: ${DISK_PCT}% (${DISK_USED} / ${DISK_TOTAL} used, ${DISK_AVAIL} free)"
            fi
        else
            warn "Could not parse disk usage percentage from: ${DISK_LINE}"
        fi
    fi
fi
echo ""

# =============================================================================
# CHECK 6: CPU temperature on Pi
# =============================================================================
echo "[ 6/9  CPU temperature (Pi) ]"

if [[ "${SSH_OK}" -eq 0 ]]; then
    warn "SSH unavailable — skipping CPU temperature check"
else
    # Try vcgencmd first (Raspberry Pi firmware tool), then fall back to
    # the thermal zone sysfs file available on all Linux systems.
    TEMP_RAW=$(ssh_run "
        if command -v vcgencmd &>/dev/null; then
            vcgencmd measure_temp 2>/dev/null
        elif [[ -f /sys/class/thermal/thermal_zone0/temp ]]; then
            raw=\$(cat /sys/class/thermal/thermal_zone0/temp)
            echo \"temp=\$(echo \"scale=1; \$raw/1000\" | bc)'C\"
        else
            echo ''
        fi
    " || echo "")

    if [[ -z "${TEMP_RAW}" ]]; then
        warn "Could not read CPU temperature — neither vcgencmd nor thermal_zone0 available"
    else
        # Parse value from "temp=47.2'C" or "temp=47.2°C"
        TEMP_VAL=$(echo "${TEMP_RAW}" | grep -oE "[0-9]+(\.[0-9]+)?" | head -1)
        TEMP_INT=$(echo "${TEMP_VAL}" | cut -d. -f1)

        if [[ -z "${TEMP_INT}" || ! "${TEMP_INT}" =~ ^[0-9]+$ ]]; then
            warn "Could not parse CPU temperature from: ${TEMP_RAW}"
        elif [[ "${TEMP_INT}" -ge 85 ]]; then
            fail "CPU temperature is critically high: ${TEMP_VAL}°C — check Pi cooling/ventilation"
            info "The Pi 5 throttles at 85°C. Ensure the active cooler is running."
        elif [[ "${TEMP_INT}" -ge "${CPU_WARN_THRESHOLD}" ]]; then
            warn "CPU temperature is elevated: ${TEMP_VAL}°C (threshold: ${CPU_WARN_THRESHOLD}°C)"
            info "Check that the Pi case fan is spinning and airflow is not blocked."
        else
            pass "CPU temperature is normal: ${TEMP_VAL}°C"
        fi
    fi
fi
echo ""

# =============================================================================
# CHECK 7: Python venv exists and is valid on Pi
# =============================================================================
echo "[ 7/9  Python venv (Pi) ]"

VENV_PATHS=("/config/aura/.venv" "/config/aura/venv")

if [[ "${SSH_OK}" -eq 0 ]]; then
    warn "SSH unavailable — skipping Python venv check"
else
    VENV_FOUND=0
    for venv_path in "${VENV_PATHS[@]}"; do
        PYTHON_BIN="${venv_path}/bin/python"
        PYTHON_CHECK=$(ssh_run "
            if [[ -f '${PYTHON_BIN}' ]]; then
                '${PYTHON_BIN}' --version 2>&1 && echo 'OK'
            else
                echo 'NOT_FOUND'
            fi
        " || echo "SSH_ERROR")

        if echo "${PYTHON_CHECK}" | grep -q "OK"; then
            PY_VER=$(echo "${PYTHON_CHECK}" | grep -oE "Python [0-9]+\.[0-9]+\.[0-9]+" | head -1)
            pass "Python venv found and valid at ${venv_path} (${PY_VER})"
            VENV_FOUND=1
            break
        fi
    done

    if [[ "${VENV_FOUND}" -eq 0 ]]; then
        warn "Python venv not found at any expected path (${VENV_PATHS[*]})"
        info "Set up the venv on the Pi:"
        info "  ssh ${PI_USER}@${PI_HOST}"
        info "  cd /config/aura && python3 -m venv .venv"
        info "  .venv/bin/pip install -r voice-agent/requirements.txt"
    fi
fi
echo ""

# =============================================================================
# CHECK 8: .env exists on Pi at /config/aura/.env
# =============================================================================
echo "[ 8/9  Pi .env file ]"

if [[ "${SSH_OK}" -eq 0 ]]; then
    warn "SSH unavailable — skipping Pi .env check"
else
    ENV_CHECK=$(ssh_run "
        if [[ -f /config/aura/.env ]]; then
            echo 'EXISTS'
            # Check permissions — should not be world-readable
            perms=\$(stat -c '%a' /config/aura/.env 2>/dev/null || stat -f '%OLp' /config/aura/.env 2>/dev/null || echo 'UNKNOWN')
            echo \"PERMS:\${perms}\"
        else
            echo 'MISSING'
        fi
    " || echo "SSH_ERROR")

    if echo "${ENV_CHECK}" | grep -q "MISSING"; then
        fail "/config/aura/.env does not exist on the Pi"
        info "Copy your .env to the Pi:"
        info "  scp ${PROJECT_ROOT}/.env ${PI_USER}@${PI_HOST}:/config/aura/.env"
        info "  ssh ${PI_USER}@${PI_HOST} 'chmod 600 /config/aura/.env'"
    elif echo "${ENV_CHECK}" | grep -q "EXISTS"; then
        PERMS=$(echo "${ENV_CHECK}" | grep "^PERMS:" | cut -d: -f2)
        if [[ "${PERMS}" == "600" || "${PERMS}" == "640" ]]; then
            pass "/config/aura/.env exists with secure permissions (${PERMS})"
        elif [[ "${PERMS}" == "UNKNOWN" ]]; then
            pass "/config/aura/.env exists (permissions could not be determined)"
        else
            warn "/config/aura/.env exists but has permissive mode ${PERMS}"
            info "Fix with: ssh ${PI_USER}@${PI_HOST} 'chmod 600 /config/aura/.env'"
        fi
    elif echo "${ENV_CHECK}" | grep -q "SSH_ERROR"; then
        warn "SSH error while checking Pi .env — result may be unreliable"
    fi
fi
echo ""

# =============================================================================
# CHECK 9: Voice agent health endpoint (port 5123)
# =============================================================================
echo "[ 9/9  Voice agent health endpoint ]"

if ! command -v curl &>/dev/null; then
    warn "curl not installed — cannot check voice agent health endpoint"
else
    # The voice agent webhook dispatcher binds to 127.0.0.1:5123 by default.
    # To reach it from the desktop, the Pi must expose it on 0.0.0.0 or we
    # need to SSH-tunnel. We attempt a direct connection first; if that fails
    # and SSH is available, we try via an SSH tunnel.
    VA_RESPONSE=$(curl --silent --max-time "${CURL_TIMEOUT}" \
        --write-out "\n---HTTP:%{http_code}" \
        "${VOICE_AGENT_HEALTH_URL}" 2>/dev/null || echo "---HTTP:000")

    VA_HTTP_CODE=$(echo "${VA_RESPONSE}" | grep "^---HTTP:" | cut -d: -f2)
    VA_BODY=$(echo "${VA_RESPONSE}" | grep -v "^---HTTP:" || true)

    if [[ "${VA_HTTP_CODE}" == "200" ]]; then
        # Extract status field from JSON without requiring jq
        VA_STATUS=$(echo "${VA_BODY}" | grep -oE '"status"\s*:\s*"[^"]*"' | \
                    grep -oE '"[^"]*"$' | tr -d '"' || echo "unknown")
        pass "Voice agent health endpoint responded HTTP 200 (status: ${VA_STATUS})"
    elif [[ "${VA_HTTP_CODE}" == "000" ]]; then
        # Direct connection failed — attempt via SSH tunnel if SSH is available
        if [[ "${SSH_OK}" -eq 1 ]]; then
            TUNNEL_BODY=$(ssh -o ConnectTimeout="${SSH_TIMEOUT}" \
                -o StrictHostKeyChecking=no \
                -o BatchMode=yes \
                -o LogLevel=ERROR \
                "${PI_USER}@${PI_HOST}" \
                "curl --silent --max-time 5 http://127.0.0.1:5123/health 2>/dev/null" \
                2>/dev/null || echo "")

            if [[ -n "${TUNNEL_BODY}" ]]; then
                VA_STATUS=$(echo "${TUNNEL_BODY}" | grep -oE '"status"\s*:\s*"[^"]*"' | \
                            grep -oE '"[^"]*"$' | tr -d '"' || echo "unknown")
                if [[ "${VA_STATUS}" == "ok" ]]; then
                    pass "Voice agent health endpoint reachable via SSH tunnel (status: ${VA_STATUS})"
                else
                    warn "Voice agent is reachable but reported status: '${VA_STATUS}'"
                    info "Check voice agent logs: journalctl -u aura_voice -n 50"
                fi
            else
                warn "Voice agent health endpoint not responding on port 5123"
                info "The /health route is only active when webhook_dispatcher.py is running"
                info "and health.py has been wired in. Check aura_voice service status."
            fi
        else
            warn "Voice agent health endpoint not reachable and SSH is unavailable"
            info "Ensure aura_voice is running and port 5123 is not firewalled."
        fi
    elif [[ "${VA_HTTP_CODE}" == "404" ]]; then
        warn "Voice agent responded HTTP 404 — /health route may not be registered yet"
        info "Wire health.py into webhook_dispatcher.py (see voice-agent/health.py)."
    else
        warn "Voice agent health endpoint returned unexpected HTTP ${VA_HTTP_CODE}"
    fi
fi
echo ""

# =============================================================================
# Summary
# =============================================================================
TOTAL=$(( PASS + WARN + FAIL ))

echo -e "${COL_HEAD}=============================================="
echo    "  Health Check Summary"
echo -e "==============================================${COL_RESET}"
printf  "  Total checks : %d\n" "${TOTAL}"
echo -e "  ${COL_PASS}Passed${COL_RESET}       : ${PASS}"
echo -e "  ${COL_WARN}Warnings${COL_RESET}     : ${WARN}"
echo -e "  ${COL_FAIL}Failed${COL_RESET}       : ${FAIL}"
echo -e "${COL_HEAD}==============================================${COL_RESET}"
echo ""

if [[ "${CRITICAL_FAIL}" -gt 0 ]]; then
    echo -e "${COL_FAIL}${FAIL} critical check(s) FAILED. AURA may not be fully operational.${COL_RESET}"
    if [[ "${WARN}" -gt 0 ]]; then
        echo "${WARN} warning(s) also found — review them when time allows."
    fi
    echo ""
    exit 1
else
    if [[ "${WARN}" -gt 0 ]]; then
        echo -e "${COL_WARN}All critical checks passed with ${WARN} warning(s). Review warnings above.${COL_RESET}"
    else
        echo -e "${COL_PASS}All checks passed. AURA is healthy.${COL_RESET}"
    fi
    echo ""
    exit 0
fi
