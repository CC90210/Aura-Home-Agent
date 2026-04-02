"""
AURA Mirror Mode — Light Choreography Engine
=============================================
Transforms a mood phrase like "ocean vibes" or "sunset feeling" into a
coordinated, multi-light color palette designed by Claude acting as a
professional lighting director.

Instead of setting every light to the same color, Mirror Mode assigns each
light entity a distinct *role* — key, fill, accent, ambient, wash — with
complementary colors, individual brightness levels, and staggered activation
so the transition feels cinematic rather than instantaneous.

Design decisions
----------------
- Claude is the creative engine.  The Python code handles HA communication,
  JSON validation, stagger timing, and graceful error recovery.  Claude does
  the lighting design.
- The Claude prompt is deliberately opinionated: it enforces the no-duplicate-
  colors rule and explains the physical context of each light type so Claude
  can make informed decisions about which role suits a floor lamp vs. an LED
  strip vs. a smart bulb.
- Each light is applied with a 0.5 s stagger so the palette cascades on in a
  defined order (key → fill → wash → accent → ambient) rather than all
  triggering at once.
- If a light entity returned by Claude does not exist in the current HA state,
  it is silently skipped.  This keeps deployments with partial hardware from
  failing loudly.
- The HA token is stored in a private header dict and is never logged.

Usage (standalone smoke-test)::

    HA_URL=http://homeassistant.local:8123 \
    HA_TOKEN=your_token \
    ANTHROPIC_API_KEY=your_key \
    python mirror_mode.py "ocean vibes"
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import requests

log = logging.getLogger("aura.mirror_mode")

# Order in which roles are applied — creates a natural "build" effect where
# the dominant key light leads and subtle ambient fills arrive last.
_ROLE_APPLY_ORDER: list[str] = ["key", "fill", "wash", "accent", "ambient"]

# Stagger delay between each light activation (seconds).
_STAGGER_DELAY: float = 0.5

# Request timeout for HA REST calls (seconds).
_HA_TIMEOUT: int = 5

# Claude model to use for palette generation.
_CLAUDE_MODEL: str = "claude-sonnet-4-6"

# Maximum tokens for the palette response.  The JSON payload is compact, so
# 800 tokens is generous without being wasteful.
_MAX_TOKENS: int = 800

# Temperature for creative lighting design — slightly elevated to encourage
# variety, but not so high that JSON structure is compromised.
_TEMPERATURE: float = 0.7


class MirrorMode:
    """
    Generates and applies coordinated multi-light color palettes driven by
    natural language mood descriptions.

    Parameters
    ----------
    ha_url:
        Base URL of the Home Assistant instance, e.g.
        ``http://homeassistant.local:8123``.
    ha_token:
        Long-lived access token for the HA REST API.
    anthropic_api_key:
        API key for the Anthropic Claude API.
    """

    def __init__(
        self,
        ha_url: str,
        ha_token: str,
        anthropic_api_key: str,
    ) -> None:
        if not ha_token:
            log.warning("HA_TOKEN is empty — HA service calls will fail.")
        if not anthropic_api_key:
            raise ValueError("anthropic_api_key must not be empty.")

        self._ha_url: str = ha_url.rstrip("/")
        self._ha_headers: dict[str, str] = {
            "Authorization": f"Bearer {ha_token}",
            "Content-Type": "application/json",
        }

        import anthropic  # type: ignore[import-untyped]

        self._client = anthropic.Anthropic(api_key=anthropic_api_key)

        log.info("MirrorMode initialised — HA: %s", self._ha_url)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def activate(self, mood_description: str) -> str:
        """
        Full pipeline: fetch lights, generate palette, apply it.

        This is the primary entry point called by the intent handler when a
        Mirror Mode command is detected.

        Parameters
        ----------
        mood_description:
            Free-text mood phrase from the user, e.g. ``"ocean vibes"``,
            ``"golden sunset"``, ``"forest at dusk"``.

        Returns
        -------
        str
            A confirmation message suitable for TTS, e.g.
            ``"Ocean Vibes is live — 5 lights choreographed."``.
        """
        log.info("Mirror Mode activating for mood: %r", mood_description)

        light_entities = self.get_current_lights()
        if not light_entities:
            log.warning("No light entities found in HA — Mirror Mode cannot activate.")
            return "I couldn't find any lights in Home Assistant right now."

        log.info("Found %d light entities.", len(light_entities))

        palette = self.generate_palette(mood_description, light_entities)
        if not palette:
            return "Something went wrong generating the lighting palette. Try again?"

        palette_name: str = palette.get("palette_name", mood_description.title())
        lights_cfg: dict[str, Any] = palette.get("lights", {})

        if not lights_cfg:
            log.warning("Claude returned an empty lights dict — nothing to apply.")
            return f"I came up with a vibe for {palette_name} but got no light assignments back."

        self.apply_palette(palette)

        applied_count = len(lights_cfg)
        log.info("Mirror Mode applied: %r — %d lights.", palette_name, applied_count)
        return (
            f"{palette_name} is live — {applied_count} light{'s' if applied_count != 1 else ''} "
            "choreographed."
        )

    def get_current_lights(self) -> list[str]:
        """
        Fetch all ``light.*`` entity IDs from Home Assistant that are currently
        available (state is not ``unavailable`` or ``unknown``).

        Returns
        -------
        list[str]
            Sorted list of entity IDs, e.g. ``["light.bedroom_leds",
            "light.living_room_leds"]``.  Returns an empty list on any error.
        """
        url = f"{self._ha_url}/api/states"
        try:
            resp = requests.get(url, headers=self._ha_headers, timeout=_HA_TIMEOUT)
            resp.raise_for_status()
            all_states: list[dict[str, Any]] = resp.json()
        except requests.exceptions.ConnectionError:
            log.warning("Cannot reach Home Assistant at %s.", self._ha_url)
            return []
        except requests.exceptions.Timeout:
            log.warning("HA /api/states request timed out.")
            return []
        except requests.exceptions.HTTPError as exc:
            log.warning("HA /api/states returned HTTP %s.", exc.response.status_code)
            return []
        except Exception as exc:  # noqa: BLE001
            log.warning("Unexpected error fetching HA states: %s", exc)
            return []

        available_lights: list[str] = [
            s["entity_id"]
            for s in all_states
            if s.get("entity_id", "").startswith("light.")
            and s.get("state") not in ("unavailable", "unknown")
        ]

        return sorted(available_lights)

    def generate_palette(
        self,
        mood_description: str,
        light_entities: list[str],
    ) -> dict[str, Any]:
        """
        Ask Claude to design a coordinated lighting palette for the given mood.

        Claude acts as a professional lighting director.  The prompt explains
        the role system (key, fill, accent, ambient, wash) and instructs Claude
        to assign complementary — never identical — colors across all lights.

        Parameters
        ----------
        mood_description:
            Free-text mood phrase, e.g. ``"ocean vibes"``.
        light_entities:
            List of HA light entity IDs to assign roles and colors to.

        Returns
        -------
        dict[str, Any]
            Parsed palette dict with the structure::

                {
                    "palette_name": "Ocean Vibes",
                    "lights": {
                        "light.living_room_leds": {
                            "role": "key",
                            "rgb": [0, 80, 180],
                            "brightness": 70
                        },
                        ...
                    }
                }

            Returns an empty dict if Claude fails to return valid JSON or if
            the API call raises an exception.
        """
        entities_str = "\n".join(f"  - {eid}" for eid in light_entities)

        prompt = f"""\
You are a world-class professional lighting designer working on a premium smart \
apartment. Your job is to create a cinematic, emotionally resonant lighting \
palette for the mood: "{mood_description}".

Available light entities:
{entities_str}

ROLE DEFINITIONS — every light must get exactly one role:
  key      — The dominant light. Brightest. Sets the primary tone and mood color.
              Think of it as the main spotlight. One key light per scene.
  fill     — Softer support for the key. Same color family but lower brightness
              and slightly warmer or cooler to add dimension.
  wash     — A broad, lower-saturation version of the mood color that fills the
              room without competing with key or fill.
  accent   — A contrasting pop of color that adds visual interest and depth.
              Should be from the complementary or split-complementary palette.
  ambient  — Very subtle background warmth or coolness. Barely visible.
              Used for LED strips behind furniture or floor-level lights.

LIGHTING DESIGN RULES (these are non-negotiable):
1. NEVER set two lights to the exact same RGB values.
2. Key light gets the highest brightness (60-90%). Ambient gets the lowest (15-35%).
3. Use the full dynamic range — vary brightness meaningfully across roles.
4. Accent must contrast with the key. If key is blue, accent could be amber/gold.
5. Consider light type when assigning roles:
   - "leds" or "strip" or "rope" in entity name → good for accent or ambient
   - "floor_lamp" or "lamp" → good for fill or wash
   - "ceiling" or "overhead" or "bulb" → good for wash or fill
   - "neon" or "bar" or "sign" → good for accent
   - "key_light" or "desk" → good for key or fill
6. RGB values must be in range [0, 255]. Brightness is 0-100 (integer, percent).
7. Create a mood-appropriate palette name (2-3 words, title case).

MOOD INTERPRETATION GUIDANCE:
- Ocean: deep blues [0-40, 80-180, 180-255], teals, sea-foam accents
- Sunset/Sunrise: warm oranges [255,120-160,0-40], pinks, deep purples ambient
- Forest: deep greens [20-60,100-160,20-60], moss accents, amber fill
- Cozy/Warm: ambers [255,140-180,0-60], warm whites, candlelight fill
- Space/Cosmic: deep purples [40-80,0-40,140-200], electric blue accents
- Party/Energy: high-saturation, cycling-style — bold primaries, contrasting accents
- Focus/Work: cool whites, subtle blue tints, minimal saturation
- Romantic: deep reds [180-220,0-40,0-30], rose accents, warm amber ambient
- Rainy Day: cool greys, slate blues, muted accents

Respond with ONLY a valid JSON object — no explanation, no markdown, no code fences.
The JSON must match this exact schema:

{{
  "palette_name": "string",
  "lights": {{
    "<entity_id>": {{
      "role": "key|fill|wash|accent|ambient",
      "rgb": [R, G, B],
      "brightness": 0-100
    }}
  }}
}}

Every entity from the list above must appear in "lights". No exceptions."""

        log.debug("Sending palette generation request to Claude for mood: %r", mood_description)
        t0 = time.monotonic()

        try:
            message = self._client.messages.create(
                model=_CLAUDE_MODEL,
                max_tokens=_MAX_TOKENS,
                temperature=_TEMPERATURE,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:  # noqa: BLE001
            log.error("Claude API call failed during palette generation: %s", exc, exc_info=True)
            return {}

        elapsed = time.monotonic() - t0
        log.debug(
            "Claude palette response in %.2f s (tokens in=%d out=%d)",
            elapsed,
            message.usage.input_tokens,
            message.usage.output_tokens,
        )

        raw_text = ""
        if message.content and hasattr(message.content[0], "text"):
            raw_text = message.content[0].text

        return self._parse_palette_response(raw_text, light_entities)

    def apply_palette(self, palette: dict[str, Any]) -> None:
        """
        Apply a generated palette to Home Assistant, staggering each light
        by :data:`_STAGGER_DELAY` seconds in role order (key first, ambient last).

        Lights whose entity IDs are not present in the current HA state are
        skipped silently so a missing physical device never blocks the rest of
        the palette from applying.

        Parameters
        ----------
        palette:
            Palette dict as returned by :meth:`generate_palette`.
        """
        lights_cfg: dict[str, Any] = palette.get("lights", {})
        if not lights_cfg:
            log.warning("apply_palette called with empty lights dict — nothing to do.")
            return

        # Group entity IDs by role so we can apply in the intended cinematic order.
        by_role: dict[str, list[str]] = {role: [] for role in _ROLE_APPLY_ORDER}
        unassigned: list[str] = []

        for entity_id, cfg in lights_cfg.items():
            role = cfg.get("role", "").lower()
            if role in by_role:
                by_role[role].append(entity_id)
            else:
                unassigned.append(entity_id)

        # Build the ordered application list: known roles first, unknowns last.
        ordered_entities: list[str] = []
        for role in _ROLE_APPLY_ORDER:
            ordered_entities.extend(by_role[role])
        ordered_entities.extend(unassigned)

        # Fetch current HA state so we can verify entity existence before calling.
        known_entity_ids = self._fetch_known_entity_ids()

        applied = 0
        skipped = 0

        for entity_id in ordered_entities:
            cfg = lights_cfg.get(entity_id, {})

            if known_entity_ids and entity_id not in known_entity_ids:
                log.warning(
                    "Skipping unknown entity %r — not found in HA state.", entity_id
                )
                skipped += 1
                continue

            self._apply_single_light(entity_id, cfg)
            applied += 1

            if applied < len(ordered_entities):
                time.sleep(_STAGGER_DELAY)

        log.info(
            "Palette applied: %d lights activated, %d skipped.", applied, skipped
        )

    # ------------------------------------------------------------------
    # Private helpers — HA integration
    # ------------------------------------------------------------------

    def _apply_single_light(self, entity_id: str, cfg: dict[str, Any]) -> None:
        """
        Call ``light.turn_on`` for a single entity with the given palette config.

        Failures are logged and swallowed so a single unavailable light does not
        interrupt the rest of the palette application.

        Parameters
        ----------
        entity_id:
            HA entity ID, e.g. ``"light.living_room_leds"``.
        cfg:
            Light config dict from the palette, containing ``rgb`` and
            ``brightness``.
        """
        rgb: list[int] | None = cfg.get("rgb")
        brightness: int | None = cfg.get("brightness")
        role: str = cfg.get("role", "unknown")

        service_data: dict[str, Any] = {"entity_id": entity_id}

        if rgb and len(rgb) == 3:
            # Clamp each channel to [0, 255] to guard against Claude rounding errors.
            service_data["rgb_color"] = [
                max(0, min(255, int(v))) for v in rgb
            ]

        if brightness is not None:
            service_data["brightness_pct"] = max(0, min(100, int(brightness)))

        url = f"{self._ha_url}/api/services/light/turn_on"
        log.debug(
            "Applying light %s (role=%s): rgb=%s brightness=%s",
            entity_id,
            role,
            rgb,
            brightness,
        )

        try:
            resp = requests.post(
                url,
                headers=self._ha_headers,
                json=service_data,
                timeout=_HA_TIMEOUT,
            )
            if resp.status_code in (200, 201):
                log.debug("light.turn_on succeeded for %s.", entity_id)
            else:
                log.warning(
                    "light.turn_on for %s returned HTTP %d: %s",
                    entity_id,
                    resp.status_code,
                    resp.text[:120],
                )
        except requests.exceptions.ConnectionError:
            log.error("Cannot reach HA to apply light %s.", entity_id)
        except requests.exceptions.Timeout:
            log.error("Timeout applying light %s.", entity_id)
        except Exception as exc:  # noqa: BLE001
            log.error("Unexpected error applying light %s: %s", entity_id, exc)

    def _fetch_known_entity_ids(self) -> set[str]:
        """
        Return all entity IDs currently registered in HA.

        Used to verify entities before calling services.  Returns an empty set
        on any error — the caller treats an empty set as "skip validation" rather
        than "all are invalid".
        """
        url = f"{self._ha_url}/api/states"
        try:
            resp = requests.get(url, headers=self._ha_headers, timeout=_HA_TIMEOUT)
            resp.raise_for_status()
            return {s.get("entity_id", "") for s in resp.json()}
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not fetch known entity IDs: %s", exc)
            return set()

    # ------------------------------------------------------------------
    # Private helpers — response parsing
    # ------------------------------------------------------------------

    def _parse_palette_response(
        self,
        raw: str,
        expected_entities: list[str],
    ) -> dict[str, Any]:
        """
        Parse Claude's raw text response into a validated palette dict.

        Tries three strategies in order:
          1. Direct ``json.loads()`` on the full string.
          2. Extract a ``\\`\\`\\`json ... \\`\\`\\``` fenced block.
          3. Extract the first ``{...}`` substring.

        After parsing, validates that the ``lights`` key exists and removes any
        entity IDs that were not in ``expected_entities`` (prevents Claude from
        hallucinating entity IDs).

        Parameters
        ----------
        raw:
            Raw text string from Claude.
        expected_entities:
            The entity list originally sent to Claude — used to filter the
            response.

        Returns
        -------
        dict[str, Any]
            Validated palette dict, or an empty dict on failure.
        """
        if not raw:
            log.warning("Empty response from Claude — cannot generate palette.")
            return {}

        parsed: dict[str, Any] | None = None

        # Strategy 1: direct parse
        try:
            result = json.loads(raw)
            if isinstance(result, dict):
                parsed = result
        except json.JSONDecodeError:
            pass

        # Strategy 2: fenced code block
        if parsed is None:
            fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
            if fence_match:
                try:
                    result = json.loads(fence_match.group(1))
                    if isinstance(result, dict):
                        parsed = result
                except json.JSONDecodeError:
                    pass

        # Strategy 3: first JSON object in the string
        if parsed is None:
            brace_match = re.search(r"\{.*\}", raw, re.DOTALL)
            if brace_match:
                try:
                    result = json.loads(brace_match.group(0))
                    if isinstance(result, dict):
                        parsed = result
                except json.JSONDecodeError:
                    pass

        if parsed is None:
            log.warning(
                "Could not parse Claude palette response as JSON. "
                "Raw (first 300 chars): %r",
                raw[:300],
            )
            return {}

        # Validate required keys
        if "lights" not in parsed or not isinstance(parsed["lights"], dict):
            log.warning("Palette response missing 'lights' dict — discarding.")
            return {}

        # Filter out any entity IDs Claude invented that are not in the known list.
        # This prevents attempting to call services on phantom entities.
        expected_set = set(expected_entities)
        filtered_lights: dict[str, Any] = {
            eid: cfg
            for eid, cfg in parsed["lights"].items()
            if eid in expected_set
        }

        if not filtered_lights:
            log.warning(
                "After filtering, no valid lights remain in palette — "
                "Claude may have returned wrong entity IDs."
            )
            return {}

        invalid_count = len(parsed["lights"]) - len(filtered_lights)
        if invalid_count > 0:
            log.warning(
                "Dropped %d hallucinated entity IDs from Claude palette response.",
                invalid_count,
            )

        parsed["lights"] = filtered_lights
        log.info(
            "Palette %r parsed — %d lights assigned.",
            parsed.get("palette_name", "Unknown"),
            len(filtered_lights),
        )
        return parsed


# ---------------------------------------------------------------------------
# Standalone smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os
    import sys
    from pathlib import Path
    from dotenv import load_dotenv

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        stream=sys.stdout,
    )

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    ha_url = os.getenv("HA_URL", "http://homeassistant.local:8123")
    ha_token = os.getenv("HA_TOKEN", "")
    api_key = os.getenv("ANTHROPIC_API_KEY", "")

    if not api_key:
        log.error("ANTHROPIC_API_KEY is not set. Exiting.")
        sys.exit(1)

    mood = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "ocean vibes"

    mirror = MirrorMode(ha_url=ha_url, ha_token=ha_token, anthropic_api_key=api_key)
    result = mirror.activate(mood)
    print(result)
