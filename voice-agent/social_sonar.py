"""
AURA Social Sonar — Intelligent Guest Detection
================================================
Detects when guests are likely present and makes subtle, ambient environment
adjustments without announcing "guest mode activated" or otherwise breaking
the social vibe.

Detection strategy
------------------
Three passive signals are combined into a confidence score:

  1. **Both residents home** — iCloud presence via HA device_tracker entities.
  2. **Evening window** — after 6 PM, guests are far more likely than midday.
  3. **Sustained audio elevation** — rolling RMS from the USB mic is higher
     during conversation than when only a TV is on, because human voices add
     spectral complexity and the RMS pattern varies continuously rather than
     sitting at a sustained fixed level from a TV.

When the composite score crosses a threshold (≥ 0.6), ``apply_social_mode``
makes three silent adjustments:
  - Slightly brighter (+10%) warm (3000K) lighting.
  - If no music is playing, starts a low-volume ambient playlist.
  - Thermostat to 21°C.

None of these changes are announced.  The HA webhook ``aura_social_sonar`` is
the entry point called from the companion automation in
``home-assistant/automations/social_sonar_monitor.yaml``.

``reset()`` reverts the environment to the stored pre-adjustment state when
audio levels drop and the score falls below the threshold.

Design decisions
----------------
- Audio sampling reuses PyAudio, which is already a dependency from
  ``wake_word.py``.  Opening a second stream is avoided — the rolling
  average is computed over the most recently stored chunk in a shared
  module-level buffer that ``wake_word.py`` can populate.  When that
  buffer is empty (e.g. no wake word listener running) the audio check
  falls back gracefully to ``None`` and reduces confidence accordingly.
- State snapshot for reset() is stored in memory only — it is not
  persisted to disk.  A restart clears it.  This is intentional: persisting
  device state correctly would require snapshotting arbitrary HA entity
  attributes, which is a large surface area for bugs.
- All HA calls use ``continue_on_error`` semantics: a single failing
  entity never aborts the sequence.

Usage (webhook path)::

    # HA fires this every 5 minutes between 6 PM and midnight
    POST http://homeassistant.local:8123/api/webhook/aura_social_sonar
    → voice agent picks up the webhook, instantiates SocialSonar, calls
      detect_social_context() then apply_social_mode() if confidence ≥ 0.6.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from typing import Any, Optional

import requests

log = logging.getLogger("aura.social_sonar")

# ---------------------------------------------------------------------------
# Shared audio ring buffer
# ---------------------------------------------------------------------------
# wake_word.py populates this list with the most recent RMS samples whenever
# it processes an audio chunk.  SocialSonar reads it to assess sustained
# audio levels without opening a competing mic stream.
#
# External code (wake_word.py or the clap listener) should call:
#   social_sonar.push_audio_rms(rms_value)
# to keep this buffer current.

_RMS_RING: list[float] = []
_RMS_RING_MAX = 50  # ~5 seconds at 1 sample per 100ms
_RMS_LOCK = threading.Lock()


def push_audio_rms(rms: float) -> None:
    """
    Push a new RMS sample into the shared ring buffer.

    Called by the audio pipeline (wake_word.py or clap_listener.py) on every
    processed chunk so SocialSonar can assess ambient noise without opening
    its own audio stream.

    Parameters
    ----------
    rms:
        Root-mean-square amplitude of the most recent audio chunk.
    """
    with _RMS_LOCK:
        _RMS_RING.append(rms)
        if len(_RMS_RING) > _RMS_RING_MAX:
            _RMS_RING.pop(0)


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

# RMS above this level is considered "elevated" (conversation-level noise).
_ELEVATED_RMS_THRESHOLD = 800.0

# Fraction of recent samples that must be elevated to trigger the audio signal.
_ELEVATED_FRACTION_REQUIRED = 0.4

# Evening starts at this hour (inclusive), 24-hour clock.
_EVENING_START_HOUR = 18

# Ambient music volume when auto-started by social sonar (0–100).
_AMBIENT_VOLUME = 20

# Brightness increase percentage when guests detected.
_BRIGHTNESS_BOOST_PCT = 10

# Target color temperature for social mode (Kelvin).
_SOCIAL_COLOR_TEMP = 3000

# Comfort temperature for social mode (°C).
_SOCIAL_TEMP_C = 21

# Ambient playlist URI to start when no music is playing.
# Override by setting SOCIAL_SONAR_PLAYLIST_URI environment variable.
_AMBIENT_PLAYLIST_URI = "spotify:playlist:37i9dQZF1DX1s9knjP51Oa"


# ---------------------------------------------------------------------------
# SocialSonar
# ---------------------------------------------------------------------------


class SocialSonar:
    """
    Detects likely guest presence and silently adjusts the apartment environment.

    Parameters
    ----------
    ha_url:
        Base URL of the Home Assistant instance.
    ha_token:
        Long-lived HA access token.
    """

    def __init__(self, ha_url: str, ha_token: str) -> None:
        if not ha_token:
            log.warning("HA_TOKEN not set — Home Assistant API calls will fail.")

        self._ha_url = ha_url.rstrip("/")
        self._ha_headers: dict[str, str] = {
            "Authorization": f"Bearer {ha_token}",
            "Content-Type": "application/json",
        }

        # Pre-adjustment state snapshot for reset()
        self._pre_adjustment_state: Optional[dict[str, Any]] = None
        self._social_mode_active = False

        log.info("SocialSonar initialised — HA: %s", self._ha_url)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect_social_context(self) -> dict[str, Any]:
        """
        Assess whether guests are likely present by combining three passive signals.

        Returns
        -------
        dict with keys:
          - ``likely_guests``  (bool)   — True when confidence ≥ 0.6
          - ``confidence``     (float)  — 0.0–1.0 composite score
          - ``indicators``     (list)   — list of active signal names
        """
        indicators: list[str] = []
        score = 0.0

        # Signal 1: Both residents home (weight 0.4)
        both_home = self._check_both_residents_home()
        if both_home:
            indicators.append("both_home")
            score += 0.4
            log.debug("Social signal: both residents home (+0.4)")

        # Signal 2: Evening window (weight 0.3)
        if self._is_evening():
            indicators.append("evening")
            score += 0.3
            log.debug("Social signal: evening window (+0.3)")

        # Signal 3: Elevated sustained audio (weight 0.3)
        audio_level = self._monitor_audio_level()
        audio_detected = (
            audio_level is not None and self._is_elevated_audio(audio_level)
        )
        if audio_detected:
            indicators.append("elevated_audio")
            score += 0.3
            log.debug(
                "Social signal: elevated audio (rms=%.1f) (+0.3)", audio_level
            )

        likely_guests = audio_detected and score >= 0.6
        confidence = round(min(score, 1.0), 2)

        log.info(
            "Social context: likely_guests=%s  confidence=%.2f  indicators=%s",
            likely_guests,
            confidence,
            indicators,
        )

        return {
            "likely_guests": likely_guests,
            "confidence": confidence,
            "indicators": indicators,
        }

    def apply_social_mode(self) -> str:
        """
        Silently adjust the environment for a social situation.

        Adjustments made:
          - All controllable lights: brightness +10%, color temp 3000K.
          - If no media is currently playing: start ambient playlist at 20%.
          - Thermostat set to 21°C.

        Nothing is announced aloud — calling code should NOT speak a
        "guest mode activated" message.  The adjustments are meant to be
        invisible to guests.

        Returns
        -------
        str
            Internal confirmation message (for logging / dashboard only —
            never sent to TTS in social context).
        """
        self._snapshot_current_state()
        self._social_mode_active = True

        steps_completed: list[str] = []

        # Step 1: Warm, slightly brighter lighting
        light_ok = self._boost_lighting()
        if light_ok:
            steps_completed.append("lighting")

        # Step 2: Background music if nothing is playing
        media_started = self._ensure_background_music()
        if media_started:
            steps_completed.append("music")

        # Step 3: Comfortable temperature
        temp_ok = self._set_temperature(_SOCIAL_TEMP_C)
        if temp_ok:
            steps_completed.append("temperature")

        result = f"Social adjustments applied: {', '.join(steps_completed)}."
        log.info(result)
        return result

    def reset(self) -> None:
        """
        Revert the apartment to the state captured before ``apply_social_mode``
        was called.

        If no snapshot exists (e.g. ``apply_social_mode`` was never called in
        this session), logs a warning and returns safely.
        """
        if not self._social_mode_active:
            log.debug("reset() called but social mode was not active — no-op.")
            return

        if self._pre_adjustment_state is None:
            log.warning(
                "reset() called but no pre-adjustment state was captured. "
                "Cannot restore previous environment."
            )
            self._social_mode_active = False
            return

        snapshot = self._pre_adjustment_state

        # Restore lights
        for entity_id, attrs in snapshot.get("lights", {}).items():
            self._call_service(
                "light",
                "turn_on",
                entity_id,
                data={
                    "brightness_pct": attrs.get("brightness_pct", 50),
                    "color_temp_kelvin": attrs.get("color_temp_kelvin", 3000),
                },
            )

        # Restore thermostat
        prev_temp = snapshot.get("thermostat_temp")
        if prev_temp is not None:
            self._set_temperature(prev_temp)

        # If we started music, stop it
        if snapshot.get("music_was_off"):
            self._call_service(
                "media_player",
                "media_pause",
                "media_player.living_room_speaker",
            )

        self._social_mode_active = False
        self._pre_adjustment_state = None
        log.info("Social sonar reset — environment restored to pre-adjustment state.")

    # ------------------------------------------------------------------
    # Private — audio
    # ------------------------------------------------------------------

    def _monitor_audio_level(self) -> Optional[float]:
        """
        Return the rolling average RMS from the shared audio ring buffer, or
        ``None`` if the buffer is empty (no audio pipeline running).

        A high sustained average indicates ongoing conversation rather than a
        single clap or a TV at fixed volume.

        Returns
        -------
        float | None
            Rolling average RMS, or None if no data is available.
        """
        with _RMS_LOCK:
            samples = list(_RMS_RING)

        if not samples:
            log.debug("Audio ring buffer is empty — no audio data available.")
            return None

        avg = sum(samples) / len(samples)
        log.debug(
            "Audio ring buffer: %d samples, avg RMS = %.1f", len(samples), avg
        )
        return avg

    def _is_elevated_audio(self, rms: float) -> bool:
        """
        Return True if the rolling RMS suggests conversation-level audio.

        Also verifies that the audio varies (non-constant) to distinguish
        real speech from a TV at a fixed level — TV audio has lower RMS
        variance relative to its mean because it's a single coherent source.
        """
        if rms < _ELEVATED_RMS_THRESHOLD:
            return False

        with _RMS_LOCK:
            samples = list(_RMS_RING)

        if len(samples) < 10:
            # Not enough samples to assess variance — accept at face value
            return True

        # Coefficient of variation: std / mean.  Speech is > ~0.3 (variable);
        # a TV at fixed volume is typically < 0.15 (steady).
        mean = sum(samples) / len(samples)
        if mean == 0:
            return False
        variance = sum((x - mean) ** 2 for x in samples) / len(samples)
        std = math.sqrt(variance)
        cv = std / mean

        # High variation at elevated RMS = conversation
        return cv > 0.25

    # ------------------------------------------------------------------
    # Private — HA checks
    # ------------------------------------------------------------------

    def _check_both_residents_home(self) -> bool:
        """Return True if both Conaugh and Adon are currently marked home."""
        entities = [
            "person.conaugh",
            "person.adon",
        ]
        for entity_id in entities:
            state = self._get_state(entity_id)
            if state != "home":
                return False
        return True

    def _is_evening(self) -> bool:
        """Return True if the current local time is in the evening window."""
        from datetime import datetime

        current_hour = datetime.now().hour
        return current_hour >= _EVENING_START_HOUR

    def _boost_lighting(self) -> bool:
        """
        Increase brightness by 10% and shift to 3000K across all lights.
        Returns True if at least one call succeeded.
        """
        light_entities = self._get_on_lights()
        if not light_entities:
            log.debug("No lights currently on — skipping brightness boost.")
            return False

        success = False
        for entity_id in light_entities:
            attrs = self._get_entity_attributes(entity_id)
            current_brightness_pct = attrs.get("brightness_pct", 50)
            new_brightness_pct = min(100, current_brightness_pct + _BRIGHTNESS_BOOST_PCT)

            ok = self._call_service(
                "light",
                "turn_on",
                entity_id,
                data={
                    "brightness_pct": new_brightness_pct,
                    "color_temp_kelvin": _SOCIAL_COLOR_TEMP,
                    "transition": 3,
                },
            )
            if ok:
                success = True

        return success

    def _ensure_background_music(self) -> bool:
        """
        Start the ambient playlist if no media is currently playing.
        Returns True if music was started.
        """
        media_state = self._get_state("media_player.living_room_speaker")
        if media_state == "playing":
            log.debug("Music already playing — not starting ambient playlist.")
            return False

        ok = self._call_service(
            "media_player",
            "play_media",
            "media_player.living_room_speaker",
            data={
                "media_content_id": _AMBIENT_PLAYLIST_URI,
                "media_content_type": "music",
            },
        )
        if ok:
            self._call_service(
                "media_player",
                "volume_set",
                "media_player.living_room_speaker",
                data={"volume_level": _AMBIENT_VOLUME / 100.0},
            )
        return ok

    def _set_temperature(self, temp_c: float) -> bool:
        """Set the thermostat to ``temp_c`` °C. Returns True on success."""
        return self._call_service(
            "climate",
            "set_temperature",
            "climate.thermostat",
            data={"temperature": temp_c},
        )

    # ------------------------------------------------------------------
    # Private — state snapshot
    # ------------------------------------------------------------------

    def _snapshot_current_state(self) -> None:
        """
        Capture the current light brightness, thermostat, and media state so
        ``reset()`` can restore them accurately.
        """
        lights: dict[str, dict[str, Any]] = {}
        for entity_id in self._get_on_lights():
            attrs = self._get_entity_attributes(entity_id)
            # HA brightness is 0-255; normalise to percentage
            raw_brightness = attrs.get("brightness", 127)
            brightness_pct = round((raw_brightness / 255.0) * 100)
            lights[entity_id] = {
                "brightness_pct": brightness_pct,
                "color_temp_kelvin": attrs.get("color_temp_kelvin"),
            }

        thermostat_attrs = self._get_entity_attributes("climate.thermostat")
        prev_temp = thermostat_attrs.get("temperature")

        media_state = self._get_state("media_player.living_room_speaker")
        music_was_off = media_state != "playing"

        self._pre_adjustment_state = {
            "lights": lights,
            "thermostat_temp": prev_temp,
            "music_was_off": music_was_off,
        }
        log.debug("Pre-adjustment state captured: %s lights, temp=%s, music_was_off=%s",
                  len(lights), prev_temp, music_was_off)

    # ------------------------------------------------------------------
    # Private — HA REST helpers
    # ------------------------------------------------------------------

    def _get_state(self, entity_id: str) -> str:
        """Return the state string for ``entity_id``, or ``"unavailable"``."""
        url = f"{self._ha_url}/api/states/{entity_id}"
        try:
            resp = requests.get(url, headers=self._ha_headers, timeout=5)
            if resp.status_code == 200:
                return resp.json().get("state", "unavailable")
            log.warning(
                "GET %s returned HTTP %d", entity_id, resp.status_code
            )
            return "unavailable"
        except requests.exceptions.RequestException as exc:
            log.warning("Cannot reach HA for state of %s: %s", entity_id, exc)
            return "unavailable"

    def _get_entity_attributes(self, entity_id: str) -> dict[str, Any]:
        """Return the attributes dict for ``entity_id``, or empty dict."""
        url = f"{self._ha_url}/api/states/{entity_id}"
        try:
            resp = requests.get(url, headers=self._ha_headers, timeout=5)
            if resp.status_code == 200:
                return resp.json().get("attributes", {})
            return {}
        except requests.exceptions.RequestException:
            return {}

    def _get_on_lights(self) -> list[str]:
        """Return entity IDs of all lights currently in state 'on'."""
        url = f"{self._ha_url}/api/states"
        try:
            resp = requests.get(url, headers=self._ha_headers, timeout=5)
            resp.raise_for_status()
            all_states: list[dict[str, Any]] = resp.json()
            return [
                s["entity_id"]
                for s in all_states
                if s.get("entity_id", "").startswith("light.")
                and s.get("state") == "on"
            ]
        except requests.exceptions.RequestException as exc:
            log.warning("Cannot fetch light states: %s", exc)
            return []

    def _call_service(
        self,
        domain: str,
        service: str,
        entity_id: str,
        data: Optional[dict[str, Any]] = None,
    ) -> bool:
        """
        Call an HA service.  Returns True on success, False on any error.
        Failures are logged and swallowed so a single failing entity never
        aborts the social mode sequence.
        """
        url = f"{self._ha_url}/api/services/{domain}/{service}"
        payload: dict[str, Any] = {"entity_id": entity_id}
        if data:
            payload.update(data)

        try:
            resp = requests.post(
                url, headers=self._ha_headers, json=payload, timeout=5
            )
            if resp.status_code in (200, 201):
                log.debug("Service %s.%s OK for %s", domain, service, entity_id)
                return True
            log.warning(
                "Service %s.%s HTTP %d: %s",
                domain,
                service,
                resp.status_code,
                resp.text[:100],
            )
            return False
        except requests.exceptions.RequestException as exc:
            log.error(
                "Cannot reach HA for %s.%s on %s: %s",
                domain,
                service,
                entity_id,
                exc,
            )
            return False
