"""
AURA Voice Agent — Security Layer
==================================
Provides safety checks for voice commands that control sensitive devices
(door locks, cameras, alarm panels). Sensitive actions require a spoken
PIN verification before execution. Certain infrastructure actions are
blocked from voice control entirely regardless of PIN.

Usage (integrated into IntentHandler._execute_action):

    guard = VoiceSecurityGuard(config_path=Path("config.yaml"))

    status, message = guard.check_action(domain, service)

    if status == "blocked":
        return message          # speak this, do not execute
    elif status == "pin_required":
        spoken_pin = await ask_user_for_pin(message)
        if not guard.verify_pin(spoken_pin):
            return "Incorrect PIN."
        # proceed with action
    else:  # "allowed"
        execute_action(domain, service, entity_id, data)

PIN storage:
    The PIN is stored as a SHA-256 hash of the string value. The raw PIN
    is never kept in memory after __init__ completes. The hash is stored
    only in memory — it is read from config.yaml at startup and never
    written back to disk.

Lockout policy:
    After MAX_FAILED_ATTEMPTS consecutive failed PIN attempts, PIN
    verification is locked out for LOCKOUT_DURATION_SECS. The lockout
    state is in-memory only — a Pi reboot resets it. This is intentional:
    physical access to reboot the Pi already implies a higher level of
    trust than a remote voice command.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path
from typing import Literal

import yaml

log = logging.getLogger("aura.security")

# ---------------------------------------------------------------------------
# Policy constants
# ---------------------------------------------------------------------------

# Actions that require PIN verification before execution.
# These are the commands that, if executed by an attacker, could cause
# physical harm or compromise the physical security of the apartment.
SENSITIVE_ACTIONS: frozenset[str] = frozenset(
    {
        "lock.unlock",
        "lock.lock",
        "lock.open",
        "alarm_control_panel.alarm_disarm",
        "alarm_control_panel.alarm_arm_away",
        "alarm_control_panel.alarm_arm_home",
        "camera.disable_motion_detection",
        "cover.open_cover",  # if covering a security-relevant window/door
    }
)

# Actions that are always blocked from voice control.
# These can only be performed via physical access to the Pi or the HA web UI.
# Allowing voice to shut down or restart HA/the Pi creates a trivial denial-
# of-service vector: an attacker who can trigger the microphone could take
# AURA offline and then enter the apartment while alarms/cameras are down.
BLOCKED_ACTIONS: frozenset[str] = frozenset(
    {
        "homeassistant.stop",
        "homeassistant.restart",
        "hassio.host_shutdown",
        "hassio.host_reboot",
        "hassio.addon_stop",
        "hassio.addon_restart",
    }
)

# Number of seconds to enforce between checking after a failed PIN attempt.
# This throttles rapid successive attempts even before the full lockout.
FAILED_PIN_COOLDOWN_SECS: float = 5.0

# Number of consecutive failed attempts before a lockout is applied.
MAX_FAILED_ATTEMPTS: int = 3

# Duration of the lockout in seconds after MAX_FAILED_ATTEMPTS is reached.
LOCKOUT_DURATION_SECS: float = 300.0  # 5 minutes

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

ActionStatus = Literal["allowed", "pin_required", "blocked"]


# ---------------------------------------------------------------------------
# VoiceSecurityGuard
# ---------------------------------------------------------------------------


class VoiceSecurityGuard:
    """
    Validates voice commands against the AURA security policy before
    they reach the Home Assistant execution layer.

    Parameters
    ----------
    config_path:
        Path to voice-agent/config.yaml. If None or the file does not
        exist, sensitive actions will be blocked (fail-safe default).
    """

    def __init__(self, config_path: Path | None = None) -> None:
        self._pin_hash: str | None = None
        self._failed_attempts: int = 0
        self._last_failed_at: float = 0.0
        self._locked_out_until: float = 0.0

        if config_path is not None and config_path.exists():
            self._load_config(config_path)
        else:
            log.warning(
                "VoiceSecurityGuard: config not found at %s — "
                "sensitive actions will be blocked until a PIN is configured.",
                config_path,
            )

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def check_action(self, domain: str, service: str) -> tuple[ActionStatus, str]:
        """
        Check whether a voice-commanded action is permitted under the
        current security policy.

        Parameters
        ----------
        domain:
            Home Assistant service domain, e.g. "lock".
        service:
            Home Assistant service name, e.g. "unlock".

        Returns
        -------
        tuple[ActionStatus, str]
            A two-tuple of (status, message):

            - ("allowed", "")
                The action can proceed without further checks.
            - ("pin_required", spoken_prompt)
                The action is sensitive. Ask the user for their PIN using
                the spoken_prompt text, then call verify_pin() with the
                response before proceeding.
            - ("blocked", reason)
                The action is never permitted via voice. Speak the reason
                text to the user and abort.
        """
        action_key = f"{domain}.{service}"

        if action_key in BLOCKED_ACTIONS:
            log.warning("Blocked action attempted via voice: %s", action_key)
            return (
                "blocked",
                f"I can't do that via voice command. "
                f"{domain} {service} must be performed through the "
                f"Home Assistant interface directly.",
            )

        if action_key in SENSITIVE_ACTIONS:
            return self._handle_sensitive_action(action_key)

        return ("allowed", "")

    def verify_pin(self, spoken_pin: str) -> bool:
        """
        Verify a spoken PIN against the configured PIN hash.

        Parameters
        ----------
        spoken_pin:
            The raw string transcribed from the user's speech. Leading
            and trailing whitespace is stripped before hashing.

        Returns
        -------
        bool
            True if the PIN matches, False otherwise.
            Returns False immediately if no PIN is configured.

        Side effects:
            On failure, increments the failed attempt counter. After
            MAX_FAILED_ATTEMPTS failures, sets a lockout timestamp.
        """
        if self._pin_hash is None:
            log.error("verify_pin called but no PIN is configured.")
            return False

        # Enforce cooldown between attempts — slows down rapid retries
        # before the full lockout kicks in.
        elapsed_since_fail = time.monotonic() - self._last_failed_at
        if self._last_failed_at > 0 and elapsed_since_fail < FAILED_PIN_COOLDOWN_SECS:
            remaining = FAILED_PIN_COOLDOWN_SECS - elapsed_since_fail
            log.warning(
                "PIN attempt during cooldown — %.1f seconds remaining.", remaining
            )
            return False

        attempt_hash = hashlib.sha256(spoken_pin.strip().encode()).hexdigest()

        if attempt_hash == self._pin_hash:
            log.info("Voice PIN verified successfully.")
            self._failed_attempts = 0
            self._last_failed_at = 0.0
            return True

        # Failed attempt
        self._failed_attempts += 1
        self._last_failed_at = time.monotonic()

        log.warning(
            "Failed voice PIN attempt %d/%d.",
            self._failed_attempts,
            MAX_FAILED_ATTEMPTS,
        )

        if self._failed_attempts >= MAX_FAILED_ATTEMPTS:
            self._locked_out_until = time.monotonic() + LOCKOUT_DURATION_SECS
            log.warning(
                "Voice PIN lockout triggered. Locked for %d seconds.",
                int(LOCKOUT_DURATION_SECS),
            )

        return False

    @property
    def is_locked_out(self) -> bool:
        """True if the PIN system is currently locked out due to failed attempts."""
        return time.monotonic() < self._locked_out_until

    @property
    def lockout_remaining_secs(self) -> int:
        """Seconds remaining in the current lockout. 0 if not locked out."""
        remaining = self._locked_out_until - time.monotonic()
        return max(0, int(remaining))

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _load_config(self, config_path: Path) -> None:
        """Load and validate the security section from config.yaml."""
        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            log.error("Failed to parse config.yaml: %s", exc)
            return
        except OSError as exc:
            log.error("Failed to read config.yaml: %s", exc)
            return

        if not isinstance(raw, dict):
            log.warning("config.yaml is not a mapping — security config skipped.")
            return

        security = raw.get("security", {})
        if not isinstance(security, dict):
            log.warning(
                "config.yaml 'security' section is not a mapping — "
                "sensitive actions will be blocked."
            )
            return

        raw_pin = os.getenv("AURA_VOICE_PIN") or security.get("voice_pin")
        if raw_pin is None:
            log.warning(
                "No voice_pin set in config.yaml security section — "
                "sensitive actions will be blocked until a PIN is configured."
            )
            return

        pin_str = str(raw_pin).strip()
        if pin_str.lower() in {"change_me", "changeme", "unset"}:
            log.warning(
                "voice_pin is still set to a placeholder value — "
                "sensitive actions will be blocked until a real PIN is configured."
            )
            return
        if len(pin_str) < 4:
            log.error(
                "voice_pin is too short (minimum 4 characters) — "
                "sensitive actions will be blocked."
            )
            return

        # Hash the PIN immediately and discard the raw value.
        self._pin_hash = hashlib.sha256(pin_str.encode()).hexdigest()
        log.info(
            "Voice PIN configured (%d characters). "
            "Sensitive actions require PIN verification.",
            len(pin_str),
        )

    def _handle_sensitive_action(
        self, action_key: str
    ) -> tuple[ActionStatus, str]:
        """Apply lockout and PIN-required logic for a sensitive action."""
        # Check lockout first
        if self.is_locked_out:
            remaining = self.lockout_remaining_secs
            log.warning(
                "Sensitive action %s blocked — PIN lockout active (%d seconds remaining).",
                action_key,
                remaining,
            )
            return (
                "blocked",
                f"PIN verification is temporarily locked after too many failed attempts. "
                f"Try again in {remaining} seconds.",
            )

        # If no PIN is configured, block the action rather than allowing
        # unguarded access to sensitive commands. Fail-safe default.
        if self._pin_hash is None:
            log.warning(
                "Sensitive action %s blocked — no voice PIN configured.", action_key
            )
            return (
                "blocked",
                "That action requires a security PIN, but none is configured. "
                "Please set a voice PIN in the AURA config before using sensitive voice commands.",
            )

        return (
            "pin_required",
            "That's a sensitive action. Please say your security PIN to confirm.",
        )
