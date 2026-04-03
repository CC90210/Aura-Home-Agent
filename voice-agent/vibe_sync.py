"""
AURA Vibe Sync
==============
Mood-adaptive lighting that breathes with whatever music is playing.

High-energy track → lights gradually brighten and shift to vibrant colors.
Chill lo-fi → lights dim and warm up.

The key design principle is *cinematically slow transitions* (15–45 seconds by
default).  The room should feel like it is breathing with the music, not
reacting to it in real time.  The user should barely notice the shift happening
— they should only notice afterward that the room feels right.

Architecture
------------
``VibeSync`` is a self-contained service object.  It has no background thread
of its own; the caller is responsible for driving ``poll_and_adjust()`` on a
regular cadence (recommended: every 60 seconds via an HA automation webhook or
a ``threading.Timer`` loop in the voice agent).

External dependencies
---------------------
- ``requests``    — HA REST API calls
- ``anthropic``   — Claude API for track mood analysis
- Environment variables ``HA_URL``, ``HA_TOKEN``, ``ANTHROPIC_API_KEY``
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

import requests

log = logging.getLogger("aura.vibe_sync")

# ---------------------------------------------------------------------------
# Light entity groups
# ---------------------------------------------------------------------------
# Primary lights receive the main color from the vibe analysis.
# Accent lights receive the secondary (accent) color at a softer level.
# These lists mirror the entity IDs expected in the HA instance.

_PRIMARY_LIGHTS: list[str] = [
    "light.living_room_leds",
    "light.key_light",
]

_ACCENT_LIGHTS: list[str] = [
    "light.bedroom_leds",
    "light.desk_accent",
]

# Default media player entity — overridden via config dict at init time.
_MEDIA_PLAYER_ENTITY: str = "media_player.living_room_speaker"

# Default model — overridden at runtime by config.yaml tiers.
_CLAUDE_MODEL: str = "claude-haiku-4-5-20251001"

# Default transition for light changes, in seconds.
_DEFAULT_TRANSITION_SECONDS: int = 30

# Minimum energy level change required to re-apply a vibe.
# Avoids micro-adjustments when tracks have similar energy.
_ENERGY_CHANGE_THRESHOLD: float = 1.5

# Claude model — overridden at runtime by config.yaml tiers.
# VibeSync uses Haiku by default (structured JSON mood classification).

# ---------------------------------------------------------------------------
# VibeSync
# ---------------------------------------------------------------------------


class VibeSync:
    """
    Analyzes currently playing music and applies a slow, atmospheric lighting
    transition that matches the track's energy and mood.

    Parameters
    ----------
    ha_url:
        Base URL of the Home Assistant instance,
        e.g. ``http://homeassistant.local:8123``.
    ha_token:
        Long-lived access token for the HA REST API.
    anthropic_api_key:
        API key for the Anthropic Claude API.  When ``None``, the key is
        read from the ``ANTHROPIC_API_KEY`` environment variable.
    config:
        Optional config overrides.  Supported keys:
          - ``transition_seconds`` (int, default 30)
          - ``media_player_entity`` (str)
          - ``primary_lights`` (list[str])
          - ``accent_lights`` (list[str])
          - ``confidence_threshold`` (float, default 0.0 — all vibes applied)
    """

    def __init__(
        self,
        ha_url: str,
        ha_token: str,
        anthropic_api_key: str | None = None,
        config: dict[str, Any] | None = None,
        claude_model: str = _CLAUDE_MODEL,
    ) -> None:
        if not ha_token:
            raise ValueError("ha_token must not be empty.")

        cfg = config or {}

        self._ha_url: str = ha_url.rstrip("/")
        self._ha_headers: dict[str, str] = {
            "Authorization": f"Bearer {ha_token}",
            "Content-Type": "application/json",
        }

        api_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError(
                "Anthropic API key is required. "
                "Pass it directly or set ANTHROPIC_API_KEY."
            )
        import anthropic  # type: ignore[import-untyped]
        self._claude = anthropic.Anthropic(api_key=api_key)

        self._claude_model = claude_model

        self._enabled: bool = False
        self._last_track: str | None = None
        self._last_energy: float | None = None

        self._transition_seconds: int = int(
            cfg.get("transition_seconds", _DEFAULT_TRANSITION_SECONDS)
        )
        self._media_player: str = cfg.get(
            "media_player_entity", _MEDIA_PLAYER_ENTITY
        )
        self._primary_lights: list[str] = cfg.get(
            "primary_lights", list(_PRIMARY_LIGHTS)
        )
        self._accent_lights: list[str] = cfg.get(
            "accent_lights", list(_ACCENT_LIGHTS)
        )

        log.info(
            "VibeSync initialised — transition=%ds  media_player=%s",
            self._transition_seconds,
            self._media_player,
        )

    # ------------------------------------------------------------------
    # Public control API
    # ------------------------------------------------------------------

    def enable(self) -> str:
        """
        Activate Vibe Sync.

        Returns
        -------
        str
            Confirmation message suitable for TTS.
        """
        self._enabled = True
        self._last_track = None  # Force a fresh analysis on next poll
        self._last_energy = None
        log.info("VibeSync enabled.")
        return "Vibe sync is on. The lights will follow the music."

    def disable(self) -> str:
        """
        Deactivate Vibe Sync.

        Returns
        -------
        str
            Confirmation message suitable for TTS.
        """
        self._enabled = False
        log.info("VibeSync disabled.")
        return "Vibe sync off. Lights are back in your hands."

    # ------------------------------------------------------------------
    # Core pipeline
    # ------------------------------------------------------------------

    def poll_and_adjust(self) -> None:
        """
        Called periodically (recommended every 60 seconds) to check whether
        the playing track has changed and apply a new vibe if needed.

        Designed to be called from an HA webhook-triggered automation, a
        ``threading.Timer`` loop, or any scheduler.  Thread-safe as long as
        only one thread calls this at a time.
        """
        if not self._enabled:
            log.debug("VibeSync is disabled — skipping poll.")
            return

        track_info = self._get_current_track()
        if not track_info:
            log.debug("Nothing is playing — no vibe adjustment.")
            return

        track_key = _make_track_key(track_info)
        if track_key == self._last_track:
            log.debug("Track unchanged (%s) — no adjustment needed.", track_key)
            return

        log.info("New track detected: %s — analyzing vibe…", track_key)
        t0 = time.monotonic()

        vibe = self.analyze_track(track_info)
        if not vibe:
            log.warning("analyze_track returned empty result — skipping apply.")
            return

        # Avoid micro-adjustments for nearly identical energy levels
        new_energy = float(vibe.get("energy", 5))
        if (
            self._last_energy is not None
            and abs(new_energy - self._last_energy) < _ENERGY_CHANGE_THRESHOLD
        ):
            log.debug(
                "Energy change %.1f → %.1f is below threshold (%.1f) — skipping.",
                self._last_energy,
                new_energy,
                _ENERGY_CHANGE_THRESHOLD,
            )
            self._last_track = track_key
            return

        self.apply_vibe(vibe, transition_seconds=self._transition_seconds)
        self._last_track = track_key
        self._last_energy = new_energy

        log.info(
            "Vibe applied in %.2f s — energy=%.0f  mood=%s  brightness=%d%%",
            time.monotonic() - t0,
            new_energy,
            vibe.get("mood", "unknown"),
            vibe.get("brightness", 0),
        )

    def analyze_track(self, track_info: dict[str, Any]) -> dict[str, Any]:
        """
        Ask Claude to classify the energy and mood of a track, and to suggest
        appropriate lighting parameters.

        Parameters
        ----------
        track_info:
            Dict containing at minimum ``title`` and ``artist``.  Optional
            fields: ``album``, ``genre``.

        Returns
        -------
        dict
            Lighting suggestion with keys::

                {
                    "energy": 7,            # 1–10
                    "mood": "vibrant",      # free-form label
                    "primary_color": [r, g, b],
                    "accent_color": [r, g, b],
                    "brightness": 70,       # 0–100
                    "color_temp": null      # Kelvin or null if RGB preferred
                }

            Returns an empty dict on any failure.
        """
        title = track_info.get("title", "Unknown")
        artist = track_info.get("artist", "Unknown")
        album = track_info.get("album", "")

        track_description = f'"{title}" by {artist}'
        if album:
            track_description += f' (from "{album}")'

        prompt = (
            f"You are an expert at matching lighting moods to music.\n\n"
            f"Current track: {track_description}\n\n"
            f"Classify this track and suggest atmospheric lighting. "
            f"Think cinematic, not nightclub — the goal is a slow, "
            f"atmospheric vibe that feels right for this music.\n\n"
            f"Return ONLY a valid JSON object with exactly these keys:\n"
            f'{{\n'
            f'  "energy": <integer 1-10>,\n'
            f'  "mood": "<one word: calm/warm/vibrant/melancholic/euphoric/tense/cozy/electric>",\n'
            f'  "primary_color": [<r>, <g>, <b>],\n'
            f'  "accent_color": [<r>, <g>, <b>],\n'
            f'  "brightness": <integer 0-100>,\n'
            f'  "color_temp": <integer Kelvin or null>\n'
            f'}}\n\n'
            f"Rules:\n"
            f"- energy 1-3: dim, warm (2700K range), soft colors\n"
            f"- energy 4-6: moderate brightness, neutral tones\n"
            f"- energy 7-9: brighter, vivid saturated colors\n"
            f"- energy 10: maximum brightness, high-saturation colors\n"
            f"- If a color fits better than a color temperature, set color_temp to null\n"
            f"- Colors should be atmospheric and feel intentional, not random\n"
            f"No explanation, no markdown fences, only the JSON object."
        )

        try:
            message = self._claude.messages.create(
                model=self._claude_model,
                max_tokens=256,
                temperature=0.4,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            log.error("Claude API call failed in analyze_track: %s", exc, exc_info=True)
            return {}

        raw = ""
        if message.content and hasattr(message.content[0], "text"):
            raw = message.content[0].text.strip()

        return self._parse_vibe_json(raw, track_description)

    def apply_vibe(
        self,
        vibe: dict[str, Any],
        transition_seconds: int = _DEFAULT_TRANSITION_SECONDS,
    ) -> None:
        """
        Apply a lighting vibe to the apartment with a slow, cinematic
        transition.

        Primary lights receive ``primary_color`` (or ``color_temp`` if RGB
        is null) at the vibe's brightness level.  Accent lights receive
        ``accent_color`` at 60–70% of the primary brightness to stay in
        the background.

        Parameters
        ----------
        vibe:
            Lighting suggestion dict as returned by ``analyze_track``.
        transition_seconds:
            Duration of the lighting transition.  Default 30 seconds.
            Passed directly to HA's ``light.turn_on`` service call so the
            transition is handled by the light controller firmware.
        """
        if not vibe:
            log.warning("apply_vibe called with empty vibe — skipping.")
            return

        brightness: int = max(5, min(100, int(vibe.get("brightness", 60))))
        primary_color: list[int] | None = vibe.get("primary_color")
        accent_color: list[int] | None = vibe.get("accent_color")
        color_temp: int | None = vibe.get("color_temp")
        transition = max(15, min(120, int(transition_seconds)))

        # Accent brightness is gentler — sits behind the primary lights
        accent_brightness = max(5, int(brightness * 0.65))

        # ── Primary lights ─────────────────────────────────────────────
        primary_data: dict[str, Any] = {
            "brightness_pct": brightness,
            "transition": transition,
        }
        if primary_color and _is_valid_rgb(primary_color):
            primary_data["rgb_color"] = primary_color[:3]
        elif color_temp:
            primary_data["color_temp"] = color_temp

        for entity_id in self._primary_lights:
            self._ha_light_turn_on(entity_id, primary_data)

        # ── Accent lights ──────────────────────────────────────────────
        accent_data: dict[str, Any] = {
            "brightness_pct": accent_brightness,
            "transition": transition,
        }
        if accent_color and _is_valid_rgb(accent_color):
            accent_data["rgb_color"] = accent_color[:3]
        elif primary_color and _is_valid_rgb(primary_color):
            # Fallback: use a softened version of the primary color
            accent_data["rgb_color"] = _soften_color(primary_color)
        elif color_temp:
            accent_data["color_temp"] = color_temp

        for entity_id in self._accent_lights:
            self._ha_light_turn_on(entity_id, accent_data)

    # ------------------------------------------------------------------
    # Home Assistant helpers
    # ------------------------------------------------------------------

    def _get_current_track(self) -> dict[str, Any] | None:
        """
        Query the HA media_player entity and return current track metadata.

        Returns
        -------
        dict | None
            ``{"title": ..., "artist": ..., "album": ...}`` when music is
            actively playing, otherwise ``None``.
        """
        url = f"{self._ha_url}/api/states/{self._media_player}"
        try:
            resp = requests.get(url, headers=self._ha_headers, timeout=5)
            resp.raise_for_status()
        except requests.exceptions.ConnectionError:
            log.warning("Cannot reach HA at %s", self._ha_url)
            return None
        except requests.exceptions.Timeout:
            log.warning("HA state query timed out for %s", self._media_player)
            return None
        except requests.exceptions.HTTPError as exc:
            log.warning("HA returned HTTP %d for %s", exc.response.status_code, self._media_player)
            return None

        data = resp.json()
        state = data.get("state", "")

        if state != "playing":
            return None

        attrs = data.get("attributes", {})
        title: str = attrs.get("media_title") or attrs.get("entity_picture", "")
        artist: str = (
            attrs.get("media_artist")
            or attrs.get("media_album_artist")
            or "Unknown Artist"
        )
        album: str = attrs.get("media_album_name", "")

        if not title:
            return None

        return {"title": title, "artist": artist, "album": album}

    def _ha_light_turn_on(
        self, entity_id: str, data: dict[str, Any]
    ) -> None:
        """
        Call ``light.turn_on`` for a single entity via the HA REST API.
        Errors are logged and swallowed so a single unreachable light does
        not abort the rest of the vibe application.
        """
        url = f"{self._ha_url}/api/services/light/turn_on"
        payload = {"entity_id": entity_id, **data}
        try:
            resp = requests.post(
                url, headers=self._ha_headers, json=payload, timeout=5
            )
            if resp.status_code not in (200, 201):
                log.warning(
                    "light.turn_on for %s returned HTTP %d",
                    entity_id,
                    resp.status_code,
                )
            else:
                log.debug(
                    "light.turn_on %s — brightness=%s  transition=%ss",
                    entity_id,
                    data.get("brightness_pct"),
                    data.get("transition"),
                )
        except requests.exceptions.ConnectionError:
            log.error("Cannot reach HA to apply vibe to %s", entity_id)
        except requests.exceptions.Timeout:
            log.error("Timeout applying vibe to %s", entity_id)
        except Exception as exc:
            log.error("Unexpected error applying vibe to %s: %s", entity_id, exc)

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _parse_vibe_json(
        self, raw: str, track_description: str
    ) -> dict[str, Any]:
        """
        Parse Claude's JSON response into a vibe dict.
        Attempts direct parse → fenced block → first braces extraction.
        """
        if not raw:
            return {}

        # Strategy 1: direct
        try:
            result = json.loads(raw)
            if isinstance(result, dict):
                return _validate_vibe(result)
        except json.JSONDecodeError:
            pass

        # Strategy 2: fenced code block
        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if fence_match:
            try:
                result = json.loads(fence_match.group(1))
                if isinstance(result, dict):
                    return _validate_vibe(result)
            except json.JSONDecodeError:
                pass

        # Strategy 3: first braces
        brace_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if brace_match:
            try:
                result = json.loads(brace_match.group(0))
                if isinstance(result, dict):
                    return _validate_vibe(result)
            except json.JSONDecodeError:
                pass

        log.warning(
            "Could not parse vibe JSON for '%s'. Raw: %r",
            track_description,
            raw[:200],
        )
        return {}


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _make_track_key(track_info: dict[str, Any]) -> str:
    """Build a stable string key from track metadata for change detection."""
    title = track_info.get("title", "")
    artist = track_info.get("artist", "")
    return f"{artist}::{title}".lower().strip()


def _is_valid_rgb(color: list[int] | None) -> bool:
    """Return True if color is a list of three ints in [0, 255]."""
    if not isinstance(color, list) or len(color) < 3:
        return False
    return all(isinstance(c, int) and 0 <= c <= 255 for c in color[:3])


def _soften_color(color: list[int]) -> list[int]:
    """
    Return a desaturated, dimmer version of a color for use as an accent.
    Blends the color 40% toward a neutral warm white so it stays atmospheric.
    """
    warm_white = [255, 220, 180]
    blend_factor = 0.4
    return [
        int(c * (1 - blend_factor) + w * blend_factor)
        for c, w in zip(color[:3], warm_white)
    ]


def _validate_vibe(data: dict[str, Any]) -> dict[str, Any]:
    """
    Clamp numeric fields into valid ranges and ensure required keys exist.
    Returns the sanitised dict, or an empty dict if required keys are missing.
    """
    required = {"energy", "mood", "brightness"}
    if not required.issubset(data.keys()):
        log.warning("Vibe dict missing required keys. Got: %s", list(data.keys()))
        return {}

    energy = max(1, min(10, int(data.get("energy", 5))))
    brightness = max(5, min(100, int(data.get("brightness", 60))))
    mood = str(data.get("mood", "neutral")).lower()

    primary_color = data.get("primary_color")
    if not _is_valid_rgb(primary_color):
        primary_color = None

    accent_color = data.get("accent_color")
    if not _is_valid_rgb(accent_color):
        accent_color = None

    color_temp = data.get("color_temp")
    if color_temp is not None:
        try:
            color_temp = int(color_temp)
            if not (1500 <= color_temp <= 9000):
                color_temp = None
        except (TypeError, ValueError):
            color_temp = None

    return {
        "energy": energy,
        "mood": mood,
        "primary_color": primary_color,
        "accent_color": accent_color,
        "brightness": brightness,
        "color_temp": color_temp,
    }
