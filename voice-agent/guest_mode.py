"""
AURA Guest Mode — Privacy Shield + Party Personality
=====================================================
When guests are over, AURA transforms:
  - Personality switches to cheeky, quick-witted, slightly unhinged
  - ALL accountability/habit nudges disabled
  - Personal data completely hidden (habits, streaks, routines, business)
  - Pulse checks paused
  - AURA becomes "the apartment's AI" — not "CC's personal assistant"

Activation:
  Voice: "Hey Aura, we have guests" / "Hey Aura, guest mode"
  HA:    input_boolean.aura_guest_mode → on
  Code:  GuestMode.activate()

Deactivation:
  Voice: "Hey Aura, guests left" / "Hey Aura, normal mode"
  HA:    input_boolean.aura_guest_mode → off
  Code:  GuestMode.deactivate()

The guest mode state persists across voice agent restarts via a JSON file.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("aura.guest_mode")

_STATE_FILE = Path("/config/aura/data/guest_mode.json")
# Fallback when not running on Pi (local development)
if not _STATE_FILE.parent.exists():
    _STATE_FILE = Path(__file__).parent.parent / "memory" / "guest_mode.json"


class GuestMode:
    """Manages guest mode state and provides guards for other modules."""

    def __init__(self):
        self._state = self._load()

    def _load(self) -> dict[str, Any]:
        try:
            if _STATE_FILE.exists():
                return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            log.debug(f"Guest mode state load failed: {e}")
        return {"active": False, "activated_at": None, "activated_by": None}

    def _save(self):
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(
            json.dumps(self._state, indent=2, default=str),
            encoding="utf-8"
        )

    @property
    def active(self) -> bool:
        return self._state.get("active", False)

    def activate(self, activated_by: str = "voice") -> str:
        """Activate guest mode. Returns the activation announcement."""
        self._state = {
            "active": True,
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "activated_by": activated_by,
        }
        self._save()
        log.info("Guest mode ACTIVATED by %s", activated_by)
        return self._get_activation_line()

    def deactivate(self) -> str:
        """Deactivate guest mode. Returns the deactivation announcement."""
        was_active = self.active
        self._state = {"active": False, "activated_at": None, "activated_by": None}
        self._save()
        log.info("Guest mode DEACTIVATED")
        if was_active:
            return "Guest mode off. Back to business. I remember everything, don't worry."
        return "Guest mode wasn't on, but we're good either way."

    def should_suppress_personal_data(self) -> bool:
        """Returns True if personal data should be hidden."""
        return self.active

    def should_suppress_accountability(self) -> bool:
        """Returns True if accountability nudges should be skipped."""
        return self.active

    def should_suppress_pulse_check(self) -> bool:
        """Returns True if pulse checks should be paused."""
        return self.active

    def get_context_override(self) -> str | None:
        """Returns 'guest' context if active, None otherwise.
        Used by the voice agent to override the auto-detected context."""
        return "guest" if self.active else None

    def _get_activation_line(self) -> str:
        """Returns a cheeky activation announcement."""
        import random
        lines = [
            "Guest mode activated. I'm just the apartment now. I don't know anybody's business, I just do lights and vibes.",
            "Switching to host mode. I'm basically a really expensive light switch that tells jokes now.",
            "Guest mode on. All personal data? Never heard of it. I'm just here for the ambiance.",
            "Welcome to the crib. I run this place. The humans just pay rent. What can I do for you?",
            "Guest mode locked in. I know nothing. I see nothing. I just make the lights pretty.",
            "Oh we got company? Say less. I'm on my best behavior. Mostly.",
        ]
        return random.choice(lines)

    # ------------------------------------------------------------------
    # Intent detection helpers
    # ------------------------------------------------------------------

    @staticmethod
    def is_activation_intent(text: str) -> bool:
        """Check if the transcribed text is asking to activate guest mode."""
        t = text.lower().strip()
        triggers = [
            "guest mode", "we have guests", "we got guests", "guests are here",
            "company over", "people over", "friends over", "friends are here",
            "guest mode on", "activate guest mode", "enable guest mode",
        ]
        return any(trigger in t for trigger in triggers)

    @staticmethod
    def is_deactivation_intent(text: str) -> bool:
        """Check if the transcribed text is asking to deactivate guest mode."""
        t = text.lower().strip()
        triggers = [
            "guests left", "guests gone", "everyone left", "they left",
            "normal mode", "guest mode off", "disable guest mode",
            "deactivate guest mode", "back to normal",
        ]
        return any(trigger in t for trigger in triggers)
