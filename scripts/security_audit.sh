#!/usr/bin/env bash
# =============================================================================
# AURA by OASIS — security_audit.sh
# Security audit for AURA installations.
#
# Checks for common misconfigurations, exposed secrets, weak authentication,
# and network exposure. Run this before deploying to a client, after rotating
# credentials, or periodically as a health check.
#
# Each check prints one of:
#   [PASS]  No issue found.
#   [WARN]  Potential issue — review and decide if action is needed.
#   [FAIL]  Definite security issue — must be fixed before deploying.
#
# Exit codes:
#   0  All checks passed (WARNs are allowed).
#   1  One or more FAIL checks were found.
#
# NOTE: Checks that only apply when running ON the Raspberry Pi (SSH key auth,
#       port exposure) are skipped gracefully when run from a desktop machine.
#
# Usage:
#   bash scripts/security_audit.sh
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Resolve repo root so all paths are absolute regardless of where this is called
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

ENV_FILE="${REPO_ROOT}/.env"
GITIGNORE_FILE="${REPO_ROOT}/.gitignore"
ENV_EXAMPLE_FILE="${REPO_ROOT}/.env.example"
VOICE_CONFIG="${REPO_ROOT}/voice-agent/config.yaml"
HA_TOKEN_TIMESTAMP_FILE="${REPO_ROOT}/.ha_token_last_rotated"

# Maximum age (in days) before warning about HA token rotation
HA_TOKEN_MAX_AGE_DAYS=90

# Counters for summary
PASS=0
WARN=0
FAIL=0

# -----------------------------------------------------------------------------
# Coloured output helpers — degrade gracefully when stdout is not a terminal
# -----------------------------------------------------------------------------
if [[ -t 1 ]]; then
  COL_PASS="\033[0;32m"   # green
  COL_WARN="\033[0;33m"   # yellow
  COL_FAIL="\033[0;31m"   # red
  COL_HEAD="\033[1;36m"   # bold cyan
  COL_RESET="\033[0m"
else
  COL_PASS=""
  COL_WARN=""
  COL_FAIL=""
  COL_HEAD=""
  COL_RESET=""
fi

pass() {
  echo -e "  ${COL_PASS}[PASS]${COL_RESET} $1"
  PASS=$((PASS + 1))
}

warn() {
  echo -e "  ${COL_WARN}[WARN]${COL_RESET} $1"
  WARN=$((WARN + 1))
}

fail() {
  echo -e "  ${COL_FAIL}[FAIL]${COL_RESET} $1"
  FAIL=$((FAIL + 1))
}

# Print a detail line (indented, no label) — used for context under a finding
detail() {
  echo "         $1"
}

# -----------------------------------------------------------------------------
# Load .env so HA_URL / HA_TOKEN are available for the HA version check
# -----------------------------------------------------------------------------
if [[ -f "${ENV_FILE}" ]]; then
  set -o allexport
  # shellcheck source=/dev/null
  source "${ENV_FILE}"
  set +o allexport
fi

# Apply defaults so the script is safe to run even without a .env file
HA_URL="${HA_URL:-http://homeassistant.local:8123}"
HA_TOKEN="${HA_TOKEN:-}"
DASHBOARD_AUTH_TOKEN="${DASHBOARD_AUTH_TOKEN:-}"

echo ""
echo -e "${COL_HEAD}=============================================="
echo    "  AURA by OASIS -- Security Audit"
echo -e "==============================================  ${COL_RESET}"
echo "  Repo root : ${REPO_ROOT}"
echo "  Date      : $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# =============================================================================
# CHECK 1: Secrets in source code
#
# Greps all Python, YAML, TypeScript, and shell files for patterns that
# indicate a hardcoded secret. False positives from placeholder strings like
# "your_*" are suppressed so only real-looking values are reported.
# =============================================================================
echo "[ 1/10  Secrets in source code ]"

# Patterns that indicate a hardcoded secret (case-insensitive where sensible).
# Each entry is a grep-compatible extended regex.
SECRET_PATTERNS=(
  "sk-[A-Za-z0-9]{20,}"                # OpenAI / Anthropic / Stripe secret keys
  "ghp_[A-Za-z0-9]{30,}"               # GitHub personal access tokens
  "eyJ[A-Za-z0-9_-]{20,}"             # JWT tokens (base64url-encoded JSON header)
  "ya29\.[A-Za-z0-9_-]{10,}"          # Google OAuth access tokens
  "AKIA[A-Z0-9]{16}"                   # AWS access key IDs
  "password\s*=\s*['\"][^'\"]{4,}['\"]"  # password = "..." or password = '...'
  "api_key\s*=\s*['\"][^'\"]{8,}['\"]"   # api_key = "..."
  "secret\s*=\s*['\"][^'\"]{8,}['\"]"    # secret = "..."
  "Bearer [A-Za-z0-9._-]{20,}"         # Inline Bearer tokens
  "token\s*=\s*['\"][^'\"]{8,}['\"]"    # token = "..."
)

# Extensions to scan — deliberately excludes node_modules, .venv, .git etc.
SCAN_EXTENSIONS=(-e "*.py" -e "*.yaml" -e "*.yml" -e "*.ts" -e "*.tsx" -e "*.sh")

# Paths to exclude from scanning entirely
EXCLUDE_DIRS=(
  "${REPO_ROOT}/.git"
  "${REPO_ROOT}/node_modules"
  "${REPO_ROOT}/dashboard/node_modules"
  "${REPO_ROOT}/.venv"
  "${REPO_ROOT}/dashboard/.next"
)

# Build the exclude arguments for grep
GREP_EXCLUDES=()
for dir in "${EXCLUDE_DIRS[@]}"; do
  GREP_EXCLUDES+=(--exclude-dir="$(basename "${dir}")")
done

SECRET_HITS=()

for pattern in "${SECRET_PATTERNS[@]}"; do
  # grep returns exit code 1 when nothing is found — we don't want that to
  # abort the script under set -e, so we capture the output with || true.
  while IFS= read -r hit; do
    # Filter out placeholder values (your_*, <your-*, example, PLACEHOLDER)
    if echo "${hit}" | grep -qiE "(your_|<your|example|placeholder|_here|_key_here|changeme)"; then
      continue
    fi
    # Filter out comment lines in YAML/shell (lines that are pure comments)
    if echo "${hit}" | grep -qE "^\s*#"; then
      continue
    fi
    SECRET_HITS+=("${hit}")
  done < <(
    grep -r --include="*.py" --include="*.yaml" --include="*.yml" \
         --include="*.ts" --include="*.tsx" --include="*.sh" \
         "${GREP_EXCLUDES[@]}" \
         -E "${pattern}" "${REPO_ROOT}" 2>/dev/null \
      | grep -v "\.env\.example" \
      | grep -v "CLAUDE\.md" \
      | grep -v "security_audit\.sh" \
      || true
  )
done

if [[ "${#SECRET_HITS[@]}" -eq 0 ]]; then
  pass "No hardcoded secrets detected in source files"
else
  fail "Potential hardcoded secrets found in source files"
  for hit in "${SECRET_HITS[@]}"; do
    detail "${hit}"
  done
  detail "Move all secrets to .env and reference them via environment variables."
fi

echo ""

# =============================================================================
# CHECK 2: .env file permissions
#
# .env must not be world-readable. Acceptable modes are 600 (owner only) or
# 640 (owner + group). 644 or 666 are failures — anyone who can log in can
# read the secrets.
# =============================================================================
echo "[ 2/10  .env file permissions ]"

if [[ -f "${ENV_FILE}" ]]; then
  if command -v stat &>/dev/null; then
    # stat -c on Linux, stat -f on macOS — detect which flavour we're on
    if stat --version &>/dev/null 2>&1; then
      # GNU stat (Linux / Alpine)
      FILE_MODE=$(stat -c "%a" "${ENV_FILE}")
    else
      # BSD stat (macOS)
      FILE_MODE=$(stat -f "%OLp" "${ENV_FILE}")
    fi

    case "${FILE_MODE}" in
      600|640)
        pass ".env permissions are ${FILE_MODE} (owner-restricted)"
        ;;
      644|660|664|666|777|*)
        fail ".env permissions are ${FILE_MODE} — should be 600 or 640"
        detail "Fix with: chmod 600 ${ENV_FILE}"
        ;;
    esac
  else
    warn "stat command not available — cannot check .env permissions"
  fi
else
  warn ".env file not found at ${ENV_FILE} — skipping permission check"
  detail "Copy .env.example to .env and fill in your values."
fi

echo ""

# =============================================================================
# CHECK 3: Git safety — .env in .gitignore and not tracked
# =============================================================================
echo "[ 3/10  Git safety ]"

# 3a — .env is listed in .gitignore
if [[ -f "${GITIGNORE_FILE}" ]]; then
  if grep -qE "^\.env$|^\.env\b" "${GITIGNORE_FILE}"; then
    pass ".env is present in .gitignore"
  else
    fail ".env is NOT in .gitignore — secrets could be committed to git"
    detail "Add '.env' to ${GITIGNORE_FILE} immediately."
  fi
else
  fail ".gitignore not found at ${GITIGNORE_FILE}"
fi

# 3b — No .env files are currently tracked by git
if command -v git &>/dev/null && git -C "${REPO_ROOT}" rev-parse --is-inside-work-tree &>/dev/null; then
  TRACKED_ENV_FILES=$(git -C "${REPO_ROOT}" ls-files | grep -E "(^|/)\.env" | grep -v "\.env\.example" || true)
  if [[ -z "${TRACKED_ENV_FILES}" ]]; then
    pass "No .env files are tracked by git"
  else
    fail "The following .env file(s) are tracked by git"
    while IFS= read -r tracked_file; do
      detail "${tracked_file}"
    done <<< "${TRACKED_ENV_FILES}"
    detail "Remove with: git rm --cached <file>  then commit the removal."
  fi
else
  warn "git not available or not a git repo — cannot check for tracked .env files"
fi

echo ""

# =============================================================================
# CHECK 4: .env.example has no real keys
#
# All values in .env.example should be placeholder strings. A real-looking key
# in .env.example means someone accidentally committed a working credential.
# =============================================================================
echo "[ 4/10  .env.example placeholder check ]"

if [[ -f "${ENV_EXAMPLE_FILE}" ]]; then
  # Extract non-comment, non-blank KEY=VALUE lines from .env.example
  REAL_KEY_LINES=()
  while IFS= read -r line; do
    # Skip blank lines and comment lines
    [[ -z "${line}" || "${line}" =~ ^[[:space:]]*# ]] && continue

    # Extract the value portion (everything after the first =)
    value="${line#*=}"

    # Strip surrounding quotes if present
    value="${value%\"}"
    value="${value#\"}"
    value="${value%\'}"
    value="${value#\'}"

    # Skip empty values
    [[ -z "${value}" ]] && continue

    # Skip clearly placeholder values and non-sensitive configuration values.
    # Non-sensitive: URLs, hostnames, paths, usernames, booleans, integers.
    if echo "${value}" | grep -qiE "^(your_|<your|http://|https://|example|placeholder|changeme|_here$|_key_here$|/callback$)"; then
      continue
    fi
    # Skip plain hostnames (e.g. homeassistant.local, localhost)
    if echo "${value}" | grep -qE "^[a-zA-Z0-9._-]+\.(local|com|io|net|org|dev)$"; then
      continue
    fi
    # Skip simple usernames (root, admin, pi, cc, adon) and filesystem paths
    if echo "${value}" | grep -qE "^(root|admin|pi|user|cc|adon)$|^[a-zA-Z0-9_/.-]+\.(db|yaml|yml|json|txt|log)$|^[a-zA-Z0-9_/-]+/$"; then
      continue
    fi
    # Skip plain integers and boolean strings
    if echo "${value}" | grep -qE "^[0-9]+$|^(true|false|yes|no|on|off)$"; then
      continue
    fi

    # If it survived all filters it may be a real value — flag it
    REAL_KEY_LINES+=("${line}")
  done < "${ENV_EXAMPLE_FILE}"

  if [[ "${#REAL_KEY_LINES[@]}" -eq 0 ]]; then
    pass ".env.example contains only placeholder values"
  else
    fail ".env.example may contain real credentials"
    for real_line in "${REAL_KEY_LINES[@]}"; do
      # Mask the value in output so the key isn't exposed in audit logs
      key_name="${real_line%%=*}"
      detail "${key_name}=<REDACTED — review manually>"
    done
    detail "Replace real values with placeholder strings like 'your_key_here'."
  fi
else
  warn ".env.example not found — cannot check for committed credentials"
fi

echo ""

# =============================================================================
# CHECK 5: HA token rotation
#
# The HA long-lived access token should be rotated periodically. We track the
# last rotation date in .ha_token_last_rotated (a plain text file containing
# a Unix timestamp — written by the operator after each rotation).
# =============================================================================
echo "[ 5/10  HA token rotation ]"

if [[ -f "${HA_TOKEN_TIMESTAMP_FILE}" ]]; then
  LAST_ROTATED=$(cat "${HA_TOKEN_TIMESTAMP_FILE}" | tr -d '[:space:]')

  # Validate that the file contains a Unix timestamp (all digits)
  if [[ "${LAST_ROTATED}" =~ ^[0-9]+$ ]]; then
    NOW=$(date +%s)
    AGE_SECONDS=$(( NOW - LAST_ROTATED ))
    AGE_DAYS=$(( AGE_SECONDS / 86400 ))

    if [[ "${AGE_DAYS}" -lt "${HA_TOKEN_MAX_AGE_DAYS}" ]]; then
      pass "HA token was rotated ${AGE_DAYS} day(s) ago (within ${HA_TOKEN_MAX_AGE_DAYS}-day limit)"
    elif [[ "${AGE_DAYS}" -lt $(( HA_TOKEN_MAX_AGE_DAYS * 2 )) ]]; then
      warn "HA token was last rotated ${AGE_DAYS} day(s) ago — consider rotating it"
      detail "Rotate in HA: Profile → Long-Lived Access Tokens → Create new token."
      detail "Then update .env and run: echo \$(date +%s) > ${HA_TOKEN_TIMESTAMP_FILE}"
    else
      fail "HA token has not been rotated in ${AGE_DAYS} day(s) (limit: ${HA_TOKEN_MAX_AGE_DAYS} days)"
      detail "Rotate in HA: Profile → Long-Lived Access Tokens → Create new token."
      detail "Then update .env and run: echo \$(date +%s) > ${HA_TOKEN_TIMESTAMP_FILE}"
    fi
  else
    warn ".ha_token_last_rotated exists but does not contain a valid Unix timestamp"
    detail "Write a fresh timestamp: echo \$(date +%s) > ${HA_TOKEN_TIMESTAMP_FILE}"
  fi
else
  warn "No HA token rotation timestamp file found at ${HA_TOKEN_TIMESTAMP_FILE}"
  detail "After rotating the HA token, record it with:"
  detail "  echo \$(date +%s) > ${HA_TOKEN_TIMESTAMP_FILE}"
  detail "This file is gitignored — it tracks rotation date locally only."
fi

echo ""

# =============================================================================
# CHECK 6: SSH key-based auth on the Pi
#
# This check only applies when running ON the Pi. When running from a desktop
# machine, sshd_config is not present locally and the check is skipped.
# =============================================================================
echo "[ 6/10  SSH key-based auth (Pi only) ]"

SSHD_CONFIG="/etc/ssh/sshd_config"

if [[ -f "${SSHD_CONFIG}" ]]; then
  # Check PasswordAuthentication — must be 'no' to enforce key-only auth
  PASSWD_AUTH=$(grep -i "^PasswordAuthentication" "${SSHD_CONFIG}" 2>/dev/null | awk '{print $2}' | tr '[:upper:]' '[:lower:]' || true)

  if [[ "${PASSWD_AUTH}" == "no" ]]; then
    pass "PasswordAuthentication is disabled — SSH requires key-based auth"
  elif [[ "${PASSWD_AUTH}" == "yes" ]]; then
    warn "PasswordAuthentication is enabled — SSH allows password login"
    detail "Disable password auth after ensuring your SSH key is installed:"
    detail "  Edit ${SSHD_CONFIG}: set PasswordAuthentication no"
    detail "  Then: service sshd restart"
  else
    warn "PasswordAuthentication directive not found in ${SSHD_CONFIG} — default may allow passwords"
    detail "Explicitly set: PasswordAuthentication no in ${SSHD_CONFIG}"
  fi

  # Also check that PermitRootLogin is not 'yes' (allow without-password is acceptable)
  ROOT_LOGIN=$(grep -i "^PermitRootLogin" "${SSHD_CONFIG}" 2>/dev/null | awk '{print $2}' | tr '[:upper:]' '[:lower:]' || true)
  if [[ "${ROOT_LOGIN}" == "yes" ]]; then
    warn "PermitRootLogin is set to 'yes' — root can log in with a password"
    detail "Set PermitRootLogin prohibit-password (allows key-based root login only)."
  elif [[ -n "${ROOT_LOGIN}" ]]; then
    pass "PermitRootLogin is '${ROOT_LOGIN}' (not plain 'yes')"
  fi
else
  warn "sshd_config not found — SSH auth check only applies when running on the Pi"
  detail "Run this script on the Pi via the SSH & Web Terminal add-on to perform this check."
fi

echo ""

# =============================================================================
# CHECK 7: Dashboard authentication token
#
# If DASHBOARD_AUTH_TOKEN is empty or unset, the Next.js dashboard has no
# authentication layer — anyone who can reach the URL can control the apartment.
# =============================================================================
echo "[ 7/10  Dashboard authentication token ]"

if [[ -n "${DASHBOARD_AUTH_TOKEN}" && "${DASHBOARD_AUTH_TOKEN}" != "your_"* ]]; then
  # Warn if the token is suspiciously short (under 32 characters)
  TOKEN_LEN=${#DASHBOARD_AUTH_TOKEN}
  if [[ "${TOKEN_LEN}" -ge 32 ]]; then
    pass "DASHBOARD_AUTH_TOKEN is set (${TOKEN_LEN} characters)"
  else
    warn "DASHBOARD_AUTH_TOKEN is set but only ${TOKEN_LEN} characters long — use at least 32"
    detail "Generate a strong token: openssl rand -hex 32"
  fi
else
  warn "DASHBOARD_AUTH_TOKEN is not set — the web dashboard has no authentication"
  detail "Add DASHBOARD_AUTH_TOKEN to .env with a strong random value."
  detail "Generate one with: openssl rand -hex 32"
  detail "The dashboard middleware must validate this token on every request."
fi

echo ""

# =============================================================================
# CHECK 8: Voice agent PIN
#
# voice-agent/config.yaml should not contain a default or empty voice_pin.
# A default PIN ("1234") or a missing PIN lets anyone trigger AURA voice
# commands if they can speak near the Pi.
# =============================================================================
echo "[ 8/10  Voice agent PIN ]"

if [[ -f "${VOICE_CONFIG}" ]]; then
  # Prefer the environment override if present, otherwise read config.yaml
  VOICE_PIN="${AURA_VOICE_PIN:-}"
  if [[ -z "${VOICE_PIN}" ]]; then
    VOICE_PIN=$(grep -E "^\s*voice_pin\s*:" "${VOICE_CONFIG}" 2>/dev/null | \
                sed -E 's/.*voice_pin\s*:\s*["\x27]?([^"'\''[:space:]]*)["\x27]?.*/\1/' || true)
  fi

  if [[ -z "${VOICE_PIN}" ]]; then
    warn "voice_pin is not configured in voice-agent/config.yaml"
    detail "Add 'voice_pin: <your_pin>' to voice-agent/config.yaml to restrict"
    detail "voice-activated commands to residents who know the PIN."
  elif [[ "${VOICE_PIN}" == "1234" || "${VOICE_PIN}" == "0000" || "${VOICE_PIN}" == "1111" || "${VOICE_PIN}" == "CHANGE_ME" ]]; then
    fail "voice_pin is set to a trivially guessable default value ('${VOICE_PIN}')"
    detail "Change voice_pin in voice-agent/config.yaml to a non-obvious value."
  else
    pass "voice_pin is configured and is not a known default"
  fi
else
  warn "voice-agent/config.yaml not found — cannot check voice PIN"
  detail "This check runs after the voice agent config is deployed."
fi

echo ""

# =============================================================================
# CHECK 9: Network exposure of port 8123
#
# Home Assistant should only be accessible on the local LAN or through a
# secured reverse proxy / VPN. If port 8123 is bound to 0.0.0.0 and the
# machine has a public IP, HA is exposed to the internet.
#
# This check only applies on the Pi. On a desktop it is skipped.
# =============================================================================
echo "[ 9/10  Network exposure of port 8123 (Pi only) ]"

if command -v ss &>/dev/null || command -v netstat &>/dev/null; then
  # Try ss first (iproute2, available on Alpine), fall back to netstat
  if command -v ss &>/dev/null; then
    PORT_LISTENERS=$(ss -tlnp 2>/dev/null | grep ":8123" || true)
  else
    PORT_LISTENERS=$(netstat -tlnp 2>/dev/null | grep ":8123" || true)
  fi

  if [[ -z "${PORT_LISTENERS}" ]]; then
    warn "Port 8123 does not appear to be listening — is Home Assistant running?"
    detail "This check is only meaningful when run on the Pi with HA active."
  else
    # Check if the port is bound to 0.0.0.0 (all interfaces) vs 127.0.0.1 (loopback only)
    # HA normally binds to 0.0.0.0 on the LAN interface — that is expected.
    # The risk is when that interface has a public IP routed from the internet.
    if echo "${PORT_LISTENERS}" | grep -qE "0\.0\.0\.0:8123|\*:8123"; then
      # Check if any network interface has a public (non-RFC-1918) IP address
      if command -v ip &>/dev/null; then
        PUBLIC_IPS=$(ip addr show 2>/dev/null | grep "inet " | \
          grep -vE "127\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.|192\.168\." | \
          grep -v "::1" || true)
      else
        PUBLIC_IPS=""
      fi

      if [[ -n "${PUBLIC_IPS}" ]]; then
        fail "Port 8123 is bound to all interfaces AND this machine has a public IP"
        detail "Public IP(s) detected:"
        while IFS= read -r ip_line; do
          detail "  ${ip_line}"
        done <<< "${PUBLIC_IPS}"
        detail "Use a reverse proxy (Caddy/Nginx) + Cloudflare Tunnel, or Nabu Casa,"
        detail "instead of exposing port 8123 directly to the internet."
      else
        pass "Port 8123 is bound to all interfaces but no public IP detected (LAN only)"
      fi
    else
      pass "Port 8123 is bound to loopback only — not directly reachable from the network"
    fi
  fi
else
  warn "ss/netstat not available — network exposure check only applies on the Pi"
  detail "Run this script on the Pi to check if port 8123 is exposed externally."
fi

echo ""

# =============================================================================
# CHECK 10: Home Assistant version (up-to-date check)
#
# Queries the HA supervisor API for the installed and latest versions.
# Requires a valid HA_TOKEN and HA_URL to be set in .env.
# =============================================================================
echo "[ 10/10 Home Assistant version check ]"

if ! command -v curl &>/dev/null; then
  warn "curl not installed — cannot query HA for version info"
elif [[ -z "${HA_TOKEN}" || "${HA_TOKEN}" == "your_"* ]]; then
  warn "HA_TOKEN is not set in .env — cannot query HA for version info"
  detail "Set HA_TOKEN in .env to enable version checking."
else
  # The /api/config endpoint returns the installed HA version
  HA_CONFIG_RESPONSE=$(curl --silent --max-time 10 \
    -H "Authorization: Bearer ${HA_TOKEN}" \
    -H "Content-Type: application/json" \
    "${HA_URL}/api/config" 2>/dev/null || true)

  if [[ -z "${HA_CONFIG_RESPONSE}" ]]; then
    warn "Could not reach Home Assistant at ${HA_URL} — is it running?"
  else
    # Extract version using basic string manipulation (no jq dependency)
    INSTALLED_VERSION=$(echo "${HA_CONFIG_RESPONSE}" | \
      grep -o '"version":"[^"]*"' | head -1 | \
      sed 's/"version":"\([^"]*\)"/\1/' || true)

    if [[ -z "${INSTALLED_VERSION}" ]]; then
      warn "Could not parse HA version from API response"
      detail "Verify HA_TOKEN is correct and HA is fully started."
    else
      # Query the supervisor for the latest available version
      # The supervisor API is only available when running ON the Pi
      LATEST_VERSION=$(curl --silent --max-time 10 \
        -H "Authorization: Bearer ${HA_TOKEN}" \
        "${HA_URL}/api/hassio/core/info" 2>/dev/null | \
        grep -o '"version_latest":"[^"]*"' | head -1 | \
        sed 's/"version_latest":"\([^"]*\)"/\1/' || true)

      if [[ -n "${LATEST_VERSION}" && "${LATEST_VERSION}" != "${INSTALLED_VERSION}" ]]; then
        warn "Home Assistant is out of date"
        detail "Installed : ${INSTALLED_VERSION}"
        detail "Latest    : ${LATEST_VERSION}"
        detail "Update via: Settings → System → Updates, or SSH: ha core update"
      elif [[ -n "${LATEST_VERSION}" ]]; then
        pass "Home Assistant is up to date (version ${INSTALLED_VERSION})"
      else
        # Supervisor endpoint unavailable — just report the installed version
        pass "Home Assistant is reachable (version ${INSTALLED_VERSION})"
        detail "Cannot determine latest version from desktop — run on Pi for full check."
      fi
    fi
  fi
fi

echo ""

# =============================================================================
# Summary
# =============================================================================
TOTAL=$((PASS + WARN + FAIL))

echo -e "${COL_HEAD}=============================================="
echo    "  Security Audit Summary"
echo -e "==============================================${COL_RESET}"
printf  "  Total checks  : %d\n" "${TOTAL}"
echo -e "  ${COL_PASS}Passed${COL_RESET}        : ${PASS}"
echo -e "  ${COL_WARN}Warnings${COL_RESET}      : ${WARN}"
echo -e "  ${COL_FAIL}Failed${COL_RESET}        : ${FAIL}"
echo -e "${COL_HEAD}==============================================${COL_RESET}"
echo ""

if [[ "${FAIL}" -gt 0 ]]; then
  echo -e "${COL_FAIL}${FAIL} check(s) FAILED. Fix all failures before deploying to a client.${COL_RESET}"
  if [[ "${WARN}" -gt 0 ]]; then
    echo "${WARN} warning(s) also found — review them when time allows."
  fi
  echo ""
  exit 1
else
  if [[ "${WARN}" -gt 0 ]]; then
    echo -e "${COL_WARN}All required checks passed with ${WARN} warning(s). Review warnings above.${COL_RESET}"
  else
    echo -e "${COL_PASS}All checks passed. AURA installation looks secure.${COL_RESET}"
  fi
  echo ""
  exit 0
fi
