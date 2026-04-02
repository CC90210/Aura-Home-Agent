"""
AURA Ghost DJ — Context-Aware Auto Music Selection
====================================================
Automatically selects and plays music based on what is happening in the
apartment: who is home, what time it is, which mode is active, and what
the residents have been listening to recently.  No "play music" command
needed — Ghost DJ watches for context transitions and steps in.

Design decisions
----------------
- Music selection is handled entirely by Claude.  The current context
  (time, person, mode, recent history) is serialised to JSON and passed as
  user content.  Claude returns a JSON object with ``playlist_uri``,
  ``volume``, and ``reason``.  This means playlist logic lives in prompts,
  not in Python, so it can be updated without a code deploy.
- Spotify playlist URIs are placeholders until the residents have Spotify
  Premium accounts.  Each placeholder URI is commented with the intended
  use case so they are easy to replace.
- ``_get_playlist_history`` reads the HA ``media_player`` state history to
  avoid repeating the same playlist twice in a row.  Falls back gracefully
  to an empty list if HA history is unavailable.
- ``should_suggest`` is deliberately conservative — it returns False unless
  a genuine context *transition* just happened (arrival, mode change, or a
  30-minute time-of-day shift).  This prevents Ghost DJ from constantly
  interrupting or overriding user-chosen music.
- All HA calls mirror the pattern in IntentHandler — sequential, logged,
  non-fatal on failure.
- The class is designed to be initialised once and called from the voice
  agent's main loop or from the webhook handler that receives the
  ``aura_ghost_dj`` webhook.

Usage (standalone, for testing):
    HA_URL=http://homeassistant.local:8123 \\
    HA_TOKEN=... \\
    ANTHROPIC_API_KEY=... \\
    python ghost_dj.py
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import requests

if TYPE_CHECKING:
    # ContextAwareness is imported from the learning package at runtime via
    # the path manipulation in aura_voice.py.  The TYPE_CHECKING guard avoids
    # a circular/optional import at module load time.
    from learning.pattern_engine import ContextAwareness

log = logging.getLogger("aura.ghost_dj")

# ---------------------------------------------------------------------------
# Spotify placeholder URIs
# ---------------------------------------------------------------------------
# Replace these with real Spotify playlist URIs once Spotify Premium is active.
# Format: spotify:playlist:<playlist_id>
# Find IDs via: open.spotify.com/playlist/<id>
#
# NOTE: These URIs are passed to Home Assistant's media_player.play_media
# service which requires the Spotify integration to be configured in HA.

_PLAYLISTS: dict[str, str] = {
    # Morning — energising, positive, starts the day right
    "morning_energy":     "spotify:playlist:placeholder_morning_energy",
    # Focused work — lo-fi, instrumental, no lyrics to distract
    "lofi_focus":         "spotify:playlist:placeholder_lofi",
    # Deep work block — binaural / ambient, maximum concentration
    "deep_work_ambient":  "spotify:playlist:placeholder_deep_work",
    # Chill evening — R&B, neo-soul, wind down
    "evening_chill":      "spotify:playlist:placeholder_evening_chill",
    # Weekend vibe — relaxed, varied, good-mood soundtrack
    "weekend_chill":      "spotify:playlist:placeholder_weekend",
    # Studio / content creation — creative energy, background beats
    "studio_beats":       "spotify:playlist:placeholder_studio",
    # DJ / music production — sample-friendly, genre-spanning
    "dj_session":         "spotify:playlist:placeholder_dj",
    # Workout — high BPM, hype, no skipping
    "workout_hype":       "spotify:playlist:placeholder_workout",
    # Party — crowd-pleasing, mix of eras
    "party_mix":          "spotify:playlist:placeholder_party",
    # Podcast break — ambient, very low-key, fills silence without distracting
    "ambient_fill":       "spotify:playlist:placeholder_ambient",
    # Late night — mellow, introspective
    "late_night_vibes":   "spotify:playlist:placeholder_late_night",
}

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Sleeping hours — Ghost DJ never auto-plays during these hours.
_SLEEP_HOURS_START = 23   # 11 PM
_SLEEP_HOURS_END = 7      # 7 AM

# HA entity ID for the living room speaker.
_DEFAULT_SPEAKER_ENTITY = "media_player.living_room_speaker"

# How many recent HA history entries to pull for playlist history.
_HISTORY_HOURS = 6
_HISTORY_LIMIT = 10

# Claude settings
_CLAUDE_MODEL = "claude-sonnet-4-6"
_CLAUDE_MAX_TOKENS = 200
_CLAUDE_TEMPERATURE = 0.4

# Modes that block Ghost DJ (recording/podcast/streaming — silence required).
_SILENT_MODES: frozenset[str] = frozenset(
    {
        "podcast_mode",
        "streaming_mode",
        "recording_mode",
    }
)

# Input booleans that represent active content/silent modes in HA.
_SILENT_MODE_ENTITIES: tuple[str, ...] = (
    "input_boolean.podcast_mode_active",
    "input_boolean.streaming_mode_active",
    "input_boolean.recording_mode_active",
)

# Do-not-disturb entity — Ghost DJ won't play if this is on.
_DND_ENTITY = "input_boolean.do_not_disturb"


# ---------------------------------------------------------------------------
# GhostDJ
# ---------------------------------------------------------------------------


class GhostDJ:
    """
    Suggests and applies context-aware music based on apartment state.

    Parameters
    ----------
    ha_url:
        Base URL of the Home Assistant instance.
    ha_token:
        Long-lived access token for the HA REST API.
    context_awareness:
        An initialised ``ContextAwareness`` instance.  Used to retrieve the
        current activity context when ``suggest_music`` is called without an
        explicit context dict.  Optional — if None, the caller must pass
        ``context`` explicitly to ``suggest_music``.
    anthropic_api_key:
        Anthropic API key.  Falls back to the ``ANTHROPIC_API_KEY`` env var.
    speaker_entity:
        HA entity ID for the primary speaker.
        Defaults to ``media_player.living_room_speaker``.
    """

    def __init__(
        self,
        ha_url: str,
        ha_token: str,
        context_awareness: "ContextAwareness | None" = None,
        anthropic_api_key: str = "",
        speaker_entity: str = _DEFAULT_SPEAKER_ENTITY,
    ) -> None:
        self._ha_url: str = ha_url.rstrip("/")
        self._ha_headers: dict[str, str] = {
            "Authorization": f"Bearer {ha_token}",
            "Content-Type": "application/json",
        }
        self._context_awareness = context_awareness
        self._speaker_entity = speaker_entity

        api_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY must be provided (or set as an environment variable)."
            )

        import anthropic  # type: ignore[import-untyped]

        self._claude = anthropic.Anthropic(api_key=api_key)

        log.info(
            "GhostDJ initialised — speaker: %s  model: %s",
            self._speaker_entity,
            _CLAUDE_MODEL,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def suggest_music(
        self,
        context: dict[str, Any],
        person: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Ask Claude to suggest a Spotify playlist and volume level for the
        current apartment context.

        Parameters
        ----------
        context:
            Dict describing the current apartment state.  Expected keys
            (all optional — Ghost DJ degrades gracefully if any are missing):

            - ``time_of_day``    (str)  — "morning" | "afternoon" | "evening" | "late_night"
            - ``hour``           (int)  — 0-23, current hour
            - ``weekday``        (bool) — True if today is Mon-Fri
            - ``active_mode``    (str)  — e.g. "studio_mode", "focus_mode", "casual"
            - ``who_is_home``    (list[str]) — resident IDs currently home
            - ``music_playing``  (bool) — True if music is already playing

        person:
            Primary resident this suggestion is for.  Used to personalise
            playlist choice (e.g. CC's DJ sessions vs Adon's sales grind).

        Returns
        -------
        dict | None
            On success: ``{"playlist_uri": str, "volume": float, "reason": str}``
            Returns None if music is already playing, conditions are not met,
            or Claude returns an unusable response.
        """
        if not self.should_suggest(context):
            log.debug("Ghost DJ: should_suggest returned False — skipping.")
            return None

        recent_history = self._get_playlist_history()
        suggestion = self._ask_claude_for_suggestion(context, person, recent_history)

        if suggestion is None:
            log.info("Ghost DJ: Claude could not produce a usable suggestion.")
            return None

        log.info(
            "Ghost DJ suggestion — playlist: %s  volume: %.0f%%  reason: %s",
            suggestion.get("playlist_uri", ""),
            suggestion.get("volume", 0) * 100,
            suggestion.get("reason", ""),
        )
        return suggestion

    def apply_music(self, suggestion: dict[str, Any]) -> None:
        """
        Apply a Ghost DJ suggestion by setting volume and starting playback
        on the primary speaker via HA media_player services.

        Parameters
        ----------
        suggestion:
            Dict returned by ``suggest_music``:
            ``{"playlist_uri": str, "volume": float, "reason": str}``

        Notes
        -----
        Failures in either the volume or playback call are logged and
        swallowed — a Ghost DJ failure must never disrupt the voice pipeline.
        """
        playlist_uri: str = suggestion.get("playlist_uri", "")
        volume: float = float(suggestion.get("volume", 0.3))
        reason: str = suggestion.get("reason", "")

        if not playlist_uri:
            log.warning("Ghost DJ: apply_music called with empty playlist_uri — skipping.")
            return

        log.info(
            "Ghost DJ applying music — uri: %s  volume: %.2f  (%s)",
            playlist_uri,
            volume,
            reason,
        )

        # ── Set volume first ───────────────────────────────────────────
        self._ha_service_call(
            domain="media_player",
            service="volume_set",
            entity_id=self._speaker_entity,
            data={"volume_level": max(0.0, min(1.0, volume))},
        )

        # ── Start playback ─────────────────────────────────────────────
        self._ha_service_call(
            domain="media_player",
            service="play_media",
            entity_id=self._speaker_entity,
            data={
                "media_content_id": playlist_uri,
                "media_content_type": "music",
            },
        )

    def should_suggest(self, context: dict[str, Any]) -> bool:
        """
        Determine whether Ghost DJ should suggest music right now.

        Returns False if any of the following are true:
        - Music is already playing on the primary speaker.
        - It is sleeping hours (11 PM – 7 AM).
        - A recording/podcast/streaming mode is active.
        - Do-not-disturb is on.

        Returns True only if a genuine context transition is present in
        ``context`` (key ``"context_transition"`` is True) AND no music
        is playing.

        Parameters
        ----------
        context:
            The same context dict passed to ``suggest_music``.

        Returns
        -------
        bool
        """
        hour: int = context.get("hour", datetime.now().hour)

        # ── Sleeping hours ─────────────────────────────────────────────
        if hour >= _SLEEP_HOURS_START or hour < _SLEEP_HOURS_END:
            log.debug("Ghost DJ: sleeping hours (%02d:00) — skipping.", hour)
            return False

        # ── Music already playing ──────────────────────────────────────
        if context.get("music_playing", False):
            log.debug("Ghost DJ: music already playing — skipping.")
            return False

        # ── Confirm no music at HA level (authoritative check) ─────────
        if self._is_music_playing():
            log.debug("Ghost DJ: HA reports music playing — skipping.")
            return False

        # ── Silent modes (recording/podcast/streaming) ─────────────────
        active_mode: str = context.get("active_mode", "")
        if active_mode in _SILENT_MODES:
            log.debug("Ghost DJ: silent mode active (%s) — skipping.", active_mode)
            return False

        if self._is_silent_mode_active():
            log.debug("Ghost DJ: HA reports a silent mode entity is on — skipping.")
            return False

        # ── Do not disturb ─────────────────────────────────────────────
        if self._is_dnd_active():
            log.debug("Ghost DJ: do-not-disturb is on — skipping.")
            return False

        # ── Context transition required ────────────────────────────────
        if not context.get("context_transition", False):
            log.debug("Ghost DJ: no context transition detected — skipping.")
            return False

        return True

    # ------------------------------------------------------------------
    # Internal — Claude integration
    # ------------------------------------------------------------------

    def _ask_claude_for_suggestion(
        self,
        context: dict[str, Any],
        person: str | None,
        recent_history: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """
        Call Claude with the current context and return a playlist suggestion.

        Claude is given the full playlist menu (with descriptions), the
        current context JSON, and the recent history to avoid repetition.
        It must return a JSON object with ``playlist_uri``, ``volume``, and
        ``reason``.

        Returns None if Claude's response cannot be parsed as a valid
        suggestion dict.
        """
        # Build the available playlists block for Claude's reference
        playlist_menu = "\n".join(
            f"  - {key}: {uri}"
            for key, uri in _PLAYLISTS.items()
        )

        # Summarise recent history so Claude avoids repeating
        if recent_history:
            history_lines = [
                f"  - {h.get('playlist', 'unknown')} at {h.get('played_at', 'unknown')}"
                for h in recent_history[:5]
            ]
            history_block = "RECENTLY PLAYED:\n" + "\n".join(history_lines)
        else:
            history_block = "RECENTLY PLAYED: none"

        person_context = (
            f"Primary resident: {person}" if person else "Resident: unknown"
        )

        system_prompt = (
            "You are Ghost DJ, the music selection module inside AURA — an AI "
            "apartment assistant created by OASIS AI Solutions.\n\n"
            "Your job is to suggest the perfect Spotify playlist and volume "
            "level for the current apartment context.  You must select from "
            "the provided playlist menu only — do not invent new URIs.\n\n"
            "PLAYLIST MENU (use the URI from this list, exactly as written):\n"
            f"{playlist_menu}\n\n"
            "VOLUME GUIDELINES:\n"
            "  - Morning routine: 0.25–0.30\n"
            "  - Focused / deep work: 0.15–0.20\n"
            "  - Casual evening (one person): 0.30–0.40\n"
            "  - Both home, evening: 0.35–0.45\n"
            "  - Weekend chill: 0.35–0.45\n"
            "  - Studio / content creation: 0.20–0.30\n"
            "  - Workout: 0.55–0.65\n"
            "  - Party: 0.65–0.75\n\n"
            "RESPONSE FORMAT — return ONLY valid JSON, nothing else:\n"
            '{"playlist_uri": "<exact URI from menu>", '
            '"volume": <0.0-1.0 float>, '
            '"reason": "<one sentence explanation>"}\n\n'
            "If no music is appropriate for this context, return:\n"
            '{"playlist_uri": null, "volume": null, "reason": "<why no music>"}'
        )

        user_message = (
            f"Select music for this context:\n\n"
            f"{person_context}\n"
            f"Context: {json.dumps(context, indent=2)}\n\n"
            f"{history_block}"
        )

        t0 = time.monotonic()
        try:
            message = self._claude.messages.create(
                model=_CLAUDE_MODEL,
                max_tokens=_CLAUDE_MAX_TOKENS,
                temperature=_CLAUDE_TEMPERATURE,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
        except Exception as exc:  # noqa: BLE001
            log.error("Ghost DJ Claude API error: %s", exc, exc_info=True)
            return None

        elapsed = time.monotonic() - t0
        log.debug("Ghost DJ Claude response in %.2f s", elapsed)

        raw = ""
        if message.content and hasattr(message.content[0], "text"):
            raw = message.content[0].text.strip()

        return self._parse_suggestion(raw)

    def _parse_suggestion(self, raw: str) -> dict[str, Any] | None:
        """
        Parse Claude's JSON response as a music suggestion.

        Returns None if:
        - The response cannot be parsed as JSON.
        - ``playlist_uri`` is null or missing.
        - ``volume`` is out of range.
        """
        if not raw:
            return None

        # Try direct parse first, then extract JSON object
        parsed: dict[str, Any] | None = None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            import re

            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass

        if not isinstance(parsed, dict):
            log.warning("Ghost DJ: could not parse Claude response as JSON: %r", raw[:200])
            return None

        playlist_uri = parsed.get("playlist_uri")
        volume = parsed.get("volume")

        if not playlist_uri:
            log.info(
                "Ghost DJ: Claude decided no music is appropriate — reason: %s",
                parsed.get("reason", ""),
            )
            return None

        if volume is None:
            log.warning("Ghost DJ: suggestion missing volume — defaulting to 0.30.")
            volume = 0.30

        try:
            volume = float(volume)
        except (TypeError, ValueError):
            log.warning("Ghost DJ: invalid volume value %r — defaulting to 0.30.", volume)
            volume = 0.30

        volume = max(0.0, min(1.0, volume))

        return {
            "playlist_uri": str(playlist_uri),
            "volume": volume,
            "reason": str(parsed.get("reason", "")),
        }

    # ------------------------------------------------------------------
    # Internal — Home Assistant queries
    # ------------------------------------------------------------------

    def _is_music_playing(self) -> bool:
        """
        Query the HA media_player state to check whether music is currently
        playing on the primary speaker.

        Returns False on any network or auth failure — Ghost DJ should
        silently skip rather than crash when HA is unreachable.
        """
        url = f"{self._ha_url}/api/states/{self._speaker_entity}"
        try:
            resp = requests.get(url, headers=self._ha_headers, timeout=5)
            if resp.status_code == 404:
                log.debug("Ghost DJ: speaker entity %s not found in HA.", self._speaker_entity)
                return False
            resp.raise_for_status()
            state: str = resp.json().get("state", "")
            return state.lower() == "playing"
        except requests.exceptions.ConnectionError:
            log.warning("Ghost DJ: cannot reach HA to check speaker state.")
            return False
        except requests.exceptions.Timeout:
            log.warning("Ghost DJ: timeout checking speaker state.")
            return False
        except Exception as exc:  # noqa: BLE001
            log.warning("Ghost DJ: unexpected error checking speaker state: %s", exc)
            return False

    def _is_silent_mode_active(self) -> bool:
        """
        Check whether any silent-mode input_boolean is currently 'on' in HA.
        Returns False if HA is unreachable.
        """
        for entity_id in _SILENT_MODE_ENTITIES:
            url = f"{self._ha_url}/api/states/{entity_id}"
            try:
                resp = requests.get(url, headers=self._ha_headers, timeout=5)
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
                if resp.json().get("state", "off").lower() == "on":
                    log.debug("Ghost DJ: silent mode entity %s is on.", entity_id)
                    return True
            except requests.exceptions.RequestException as exc:
                log.debug("Ghost DJ: error checking %s: %s", entity_id, exc)
        return False

    def _is_dnd_active(self) -> bool:
        """
        Check whether do-not-disturb is on in HA.
        Returns False if the entity is missing or HA is unreachable.
        """
        url = f"{self._ha_url}/api/states/{_DND_ENTITY}"
        try:
            resp = requests.get(url, headers=self._ha_headers, timeout=5)
            if resp.status_code == 404:
                return False
            resp.raise_for_status()
            return resp.json().get("state", "off").lower() == "on"
        except requests.exceptions.RequestException as exc:
            log.debug("Ghost DJ: error checking DND entity: %s", exc)
            return False

    def _get_playlist_history(self) -> list[dict[str, Any]]:
        """
        Read recent playlist plays from the HA ``logbook`` endpoint for the
        primary speaker entity over the last ``_HISTORY_HOURS`` hours.

        The logbook returns state-change events which include
        ``media_content_id`` in the message for media_player entities when the
        Spotify integration is active.

        Returns an empty list on any failure — history is advisory only.
        """
        since = (
            datetime.now(timezone.utc) - timedelta(hours=_HISTORY_HOURS)
        ).isoformat()

        url = (
            f"{self._ha_url}/api/logbook/{since}"
            f"?entity_id={self._speaker_entity}&limit={_HISTORY_LIMIT}"
        )
        try:
            resp = requests.get(url, headers=self._ha_headers, timeout=8)
            if resp.status_code in (404, 405):
                # Logbook endpoint may not be available in all HA versions
                return []
            resp.raise_for_status()
            entries: list[dict[str, Any]] = resp.json()
        except requests.exceptions.RequestException as exc:
            log.debug("Ghost DJ: could not fetch playlist history: %s", exc)
            return []
        except (json.JSONDecodeError, ValueError):
            return []

        # Extract media_content_id from logbook entries where it appears
        history: list[dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            message: str = entry.get("message", "")
            when: str = entry.get("when", "")
            # The HA logbook message for Spotify often contains the URI
            if "spotify:playlist" in message:
                # Extract the URI from the message string
                import re

                match = re.search(r"spotify:playlist:[^\s\"']+", message)
                if match:
                    history.append({"playlist": match.group(0), "played_at": when})

        log.debug("Ghost DJ: found %d recent playlist history entries.", len(history))
        return history

    def _ha_service_call(
        self,
        domain: str,
        service: str,
        entity_id: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """
        Execute a Home Assistant service call.  Non-fatal — failures are
        logged and the caller continues normally.
        """
        url = f"{self._ha_url}/api/services/{domain}/{service}"
        payload: dict[str, Any] = {"entity_id": entity_id}
        if data:
            payload.update(data)

        log.info("Ghost DJ HA call: %s.%s  entity=%s  data=%s", domain, service, entity_id, data)

        try:
            resp = requests.post(url, headers=self._ha_headers, json=payload, timeout=5)
            if resp.status_code not in (200, 201):
                log.warning(
                    "Ghost DJ: %s.%s returned HTTP %d: %s",
                    domain,
                    service,
                    resp.status_code,
                    resp.text[:120],
                )
        except requests.exceptions.ConnectionError:
            log.error("Ghost DJ: cannot reach HA for %s.%s", domain, service)
        except requests.exceptions.Timeout:
            log.error("Ghost DJ: timeout on %s.%s", domain, service)
        except Exception as exc:  # noqa: BLE001
            log.error("Ghost DJ: unexpected error on %s.%s: %s", domain, service, exc)


# ---------------------------------------------------------------------------
# CLI entry point (manual testing)
# ---------------------------------------------------------------------------


def _cli() -> None:
    """
    Usage
    -----
    python ghost_dj.py
    python ghost_dj.py --apply
    """
    import argparse
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        stream=sys.stdout,
    )

    parser = argparse.ArgumentParser(description="AURA Ghost DJ — standalone CLI")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the suggestion to the speaker via HA (default: dry run, just print).",
    )
    parser.add_argument("--person", default="conaugh", choices=["conaugh", "adon"])
    args = parser.parse_args()

    ha_url = os.getenv("HA_URL", "http://homeassistant.local:8123")
    ha_token = os.getenv("HA_TOKEN", "")

    dj = GhostDJ(ha_url=ha_url, ha_token=ha_token)

    now = datetime.now()
    hour = now.hour
    weekday = now.weekday() < 5

    if hour < 12:
        tod = "morning"
    elif hour < 18:
        tod = "afternoon"
    elif hour < 23:
        tod = "evening"
    else:
        tod = "late_night"

    test_context: dict[str, Any] = {
        "time_of_day": tod,
        "hour": hour,
        "weekday": weekday,
        "active_mode": "casual",
        "who_is_home": [args.person],
        "music_playing": False,
        "context_transition": True,   # Force a suggestion for testing
    }

    log.info("Testing Ghost DJ with context: %s", json.dumps(test_context, indent=2))

    suggestion = dj.suggest_music(test_context, person=args.person)

    if suggestion:
        log.info("Suggestion: %s", json.dumps(suggestion, indent=2))
        if args.apply:
            log.info("Applying suggestion to speaker…")
            dj.apply_music(suggestion)
        else:
            log.info("Dry run — pass --apply to actually play music.")
    else:
        log.info("No suggestion returned (conditions not met or Claude said no music).")


if __name__ == "__main__":
    _cli()
