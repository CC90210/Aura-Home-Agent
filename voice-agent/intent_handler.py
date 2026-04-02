"""
AURA Intent Handler
===================
The core intelligence of the voice agent.  Accepts transcribed text from
the user, queries the current Home Assistant device states, builds a
context-rich system prompt, and sends the conversation to Claude.

Claude responds with a JSON object containing:
  - "response"  — natural language text for AURA to speak aloud
  - "actions"   — list of Home Assistant service calls to execute

Each action is then dispatched to the HA REST API.

Design decisions
----------------
- Claude is given ONLY the entities that are likely relevant (lights,
  switches, media_players, climate, locks, cover) to keep the prompt
  concise and reduce token usage.  Sensor-only entities are excluded.
- If Claude returns malformed JSON, a best-effort parse is attempted
  (extracting the JSON block from the response text) before giving up.
- HA service calls are executed sequentially.  A failure in one action
  is logged and skipped; remaining actions still execute.
- The HA token is passed as a Bearer header, never logged.
- The system prompt is built by AuraPersonality so personality, resident
  context, and habit data are always included without duplicating logic here.
- The current speaker and active context are supplied by the caller via
  ``process()``.  IntentHandler itself has no opinion on who is talking.

Usage (standalone, for testing):
    HA_URL=http://homeassistant.local:8123 \
    HA_TOKEN=... \
    ANTHROPIC_API_KEY=... \
    python intent_handler.py
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

import requests

from personality import AuraPersonality
from capabilities import AuraCapabilities

try:
    from security import VoiceSecurityGuard
    _SECURITY_AVAILABLE = True
except ImportError:
    _SECURITY_AVAILABLE = False

log = logging.getLogger("aura.intent")

# Path to personality.yaml — sibling of this file.
_PERSONALITY_YAML = Path(__file__).resolve().parent / "personality.yaml"

# Path to capabilities.yaml — sibling of this file.
_CAPABILITIES_YAML = Path(__file__).resolve().parent / "capabilities.yaml"

# HA entity domains that AURA can meaningfully control.
_CONTROLLABLE_DOMAINS = frozenset(
    {
        "light",
        "switch",
        "media_player",
        "climate",
        "lock",
        "cover",
        "fan",
        "vacuum",
        "scene",
        "script",
        "input_boolean",
        "automation",
    }
)

# Maximum number of entities to include in the system prompt.
# Keeps token usage predictable even in large HA installations.
_MAX_ENTITIES_IN_PROMPT = 60

# Claude JSON response keys
_RESPONSE_KEY = "response"
_ACTIONS_KEY = "actions"


class IntentHandler:
    """
    Processes natural language commands by combining real-time Home Assistant
    state with Claude's reasoning to produce both a spoken response and a
    list of device actions.

    Parameters
    ----------
    ha_url:
        Base URL of the Home Assistant instance, e.g.
        ``http://homeassistant.local:8123``.
    ha_token:
        Long-lived access token for the HA REST API.
    anthropic_api_key:
        API key for the Anthropic Claude API.
    config:
        The full config dict.  Reads from ``claude`` and ``protocols``
        sections.

    Notes
    -----
    ``AuraPersonality`` is initialised once here and reused across all
    ``process()`` calls.  If ``personality.yaml`` is missing, a warning is
    logged and the handler falls back to the legacy static system prompt so
    the voice pipeline continues to function.
    """

    def __init__(
        self,
        ha_url: str,
        ha_token: str,
        anthropic_api_key: str,
        config: dict[str, Any],
    ) -> None:
        if not ha_token:
            log.warning(
                "HA_TOKEN is not set — Home Assistant API calls will fail."
            )
        if not anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY must not be empty.")

        self._ha_url: str = ha_url.rstrip("/")
        self._ha_headers: dict[str, str] = {
            "Authorization": f"Bearer {ha_token}",
            "Content-Type": "application/json",
        }

        claude_cfg = config.get("claude", {})
        self._claude_model: str = claude_cfg.get("model", "claude-sonnet-4-6")
        self._max_tokens: int = int(claude_cfg.get("max_tokens", 500))
        self._temperature: float = float(claude_cfg.get("temperature", 0.3))
        self._protocols: dict[str, Any] = config.get("protocols", {})

        import anthropic  # type: ignore[import-untyped]

        self._client = anthropic.Anthropic(api_key=anthropic_api_key)

        # Initialise the personality engine.  A missing personality.yaml is
        # non-fatal — the pipeline degrades to a minimal static prompt.
        self._personality: AuraPersonality | None = None
        try:
            self._personality = AuraPersonality(_PERSONALITY_YAML)
            log.info("AuraPersonality loaded successfully.")
        except FileNotFoundError:
            log.warning(
                "personality.yaml not found at %s — using fallback system prompt.",
                _PERSONALITY_YAML,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "Failed to load AuraPersonality: %s — using fallback system prompt.",
                exc,
            )

        # Initialise the security guard.  Non-fatal — if the module or config
        # is missing, sensitive actions default to blocked (safe failure mode).
        self._security = None  # type: ignore[assignment]
        if _SECURITY_AVAILABLE:
            try:
                self._security = VoiceSecurityGuard(
                    config_path=Path(__file__).resolve().parent / "config.yaml"
                )
                log.info("VoiceSecurityGuard loaded.")
            except Exception as exc:  # noqa: BLE001
                log.warning("Failed to load VoiceSecurityGuard: %s", exc)
        else:
            log.warning("security.py not found — voice security guard disabled.")

        # Initialise the capabilities registry.  Always non-fatal — the
        # instance degrades gracefully to empty strings when the YAML is
        # missing, so the pipeline keeps running.
        self._capabilities = AuraCapabilities(_CAPABILITIES_YAML)
        log.info("AuraCapabilities loaded.")

        log.info(
            "IntentHandler initialised — HA: %s  model: %s  max_tokens: %d",
            self._ha_url,
            self._claude_model,
            self._max_tokens,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(
        self,
        user_text: str,
        person: str | None = None,
        context: str = "casual",
        time_of_day: str | None = None,
        habit_data: dict[str, Any] | None = None,
    ) -> str:
        """
        Process a transcribed user command end-to-end.

        1. Fetch current HA device states.
        2. Build a personality-aware system prompt via AuraPersonality.
        3. Send user text + system prompt to Claude.
        4. Parse Claude's JSON response.
        5. Execute any HA service calls returned.
        6. Return the natural language response string for TTS.

        Parameters
        ----------
        user_text:
            Transcribed speech from the user.
        person:
            Resident ID of the speaker (``"conaugh"`` / ``"adon"``), or
            ``None`` if unknown.  Provided by ``PersonRecognizer``.
        context:
            Active context from ``personality.VALID_CONTEXTS`` — e.g.
            ``"casual"``, ``"working"``, ``"creating_content"``.
            Provided by ``ContextAwareness`` from the learning module.
            Defaults to ``"casual"``.
        time_of_day:
            Current time as ``"HH:MM"`` or a band name (``"morning"`` etc.).
            Defaults to the current system clock when ``None``.
        habit_data:
            Habit tracking snapshot from ``HabitTracker`` keyed by habit name.
            Passed through to ``AuraPersonality`` so Claude can reference
            streaks and misses naturally in conversation.

        Returns
        -------
        str
            The natural language response for AURA to speak.
            Returns a safe fallback string on any error.
        """
        if not user_text or not user_text.strip():
            log.warning("process() called with empty text — returning default.")
            return "I didn't catch that. Could you try again?"

        log.info(
            "Processing command: %r  (person=%s, context=%s)",
            user_text,
            person,
            context,
        )
        t0 = time.monotonic()

        # Step 1: Fetch device state snapshot
        device_states = self._get_device_states()

        # Step 2: Build personality-aware system prompt
        system_prompt = self._build_system_prompt(
            device_states,
            person=person,
            context=context,
            time_of_day=time_of_day,
            habit_data=habit_data,
        )

        # Step 3: Call Claude
        try:
            raw_response = self._call_claude(system_prompt, user_text)
        except Exception as exc:  # noqa: BLE001
            log.error("Claude API call failed: %s", exc, exc_info=True)
            return "Sorry, I had trouble thinking about that. Please try again."

        # Step 4: Parse response
        parsed = self._parse_response(raw_response)
        response_text: str = parsed.get(_RESPONSE_KEY, "")
        actions: list[dict[str, Any]] = parsed.get(_ACTIONS_KEY, [])

        if not response_text:
            log.warning("Claude response missing 'response' key — using fallback.")
            response_text = "Done."

        # Step 5: Execute actions
        if actions:
            log.info("Executing %d HA action(s)…", len(actions))
            for action in actions:
                self._execute_action(action)
        else:
            log.debug("No HA actions in Claude response.")

        elapsed = time.monotonic() - t0
        log.info("Intent processed in %.2f s — response: %r", elapsed, response_text[:80])
        return response_text

    # ------------------------------------------------------------------
    # Home Assistant integration
    # ------------------------------------------------------------------

    def _get_device_states(self) -> list[dict[str, Any]]:
        """
        Fetch all entity states from the HA REST API and return only the
        controllable entities (lights, switches, media players, etc.).

        Returns an empty list on any network or auth failure so the pipeline
        can still proceed (Claude will respond without live state context).
        """
        url = f"{self._ha_url}/api/states"
        try:
            resp = requests.get(url, headers=self._ha_headers, timeout=5)
            resp.raise_for_status()
            all_states: list[dict[str, Any]] = resp.json()
        except requests.exceptions.ConnectionError:
            log.warning("Cannot reach Home Assistant at %s — proceeding without device state.", self._ha_url)
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

        # Filter to controllable domains only and cap the count
        controllable = [
            s for s in all_states
            if s.get("entity_id", "").split(".")[0] in _CONTROLLABLE_DOMAINS
        ]
        log.debug(
            "Fetched %d total states, %d controllable.",
            len(all_states),
            len(controllable),
        )
        return controllable[:_MAX_ENTITIES_IN_PROMPT]

    def _execute_action(self, action: dict[str, Any]) -> None:
        """
        Execute a single Home Assistant service call.

        The action dict must contain:
          - domain      (str)  — e.g. "light"
          - service     (str)  — e.g. "turn_on"
          - entity_id   (str)  — e.g. "light.living_room_leds"
          - data        (dict) — optional extra service data (brightness, etc.)

        Failures are logged and swallowed so subsequent actions still run.
        """
        domain = action.get("domain", "")
        service = action.get("service", "")
        entity_id = action.get("entity_id", "")
        extra_data: dict[str, Any] = action.get("data", {}) or {}

        if not domain or not service:
            log.warning("Skipping malformed action (missing domain or service): %s", action)
            return

        # Security check — block or require PIN for sensitive actions
        if self._security:
            status, message = self._security.check_action(domain, service)
            if status == "blocked":
                log.warning("BLOCKED by security policy: %s.%s — %s", domain, service, message)
                return
            if status == "pin_required":
                log.warning("PIN required for %s.%s — action skipped (voice PIN flow not yet wired)", domain, service)
                return

        url = f"{self._ha_url}/api/services/{domain}/{service}"
        payload: dict[str, Any] = {**extra_data}
        if entity_id:
            payload["entity_id"] = entity_id

        log.info("HA action: %s.%s  entity=%s  data=%s", domain, service, entity_id, extra_data)

        try:
            resp = requests.post(url, headers=self._ha_headers, json=payload, timeout=5)
            if resp.status_code in (200, 201):
                log.debug("Action %s.%s executed successfully.", domain, service)
            else:
                log.warning(
                    "HA service %s.%s returned HTTP %d: %s",
                    domain,
                    service,
                    resp.status_code,
                    resp.text[:120],
                )
        except requests.exceptions.ConnectionError:
            log.error("Cannot reach HA to execute %s.%s", domain, service)
        except requests.exceptions.Timeout:
            log.error("Timeout executing HA action %s.%s", domain, service)
        except Exception as exc:  # noqa: BLE001
            log.error("Unexpected error executing %s.%s: %s", domain, service, exc)

    # ------------------------------------------------------------------
    # Claude integration
    # ------------------------------------------------------------------

    def _call_claude(self, system_prompt: str, user_text: str) -> str:
        """
        Send the system prompt and user message to Claude and return the
        raw text content of the first response block.
        """
        log.debug("Calling Claude %s…", self._claude_model)
        t0 = time.monotonic()

        message = self._client.messages.create(
            model=self._claude_model,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_text},
            ],
        )

        elapsed = time.monotonic() - t0
        log.debug(
            "Claude responded in %.2f s (input_tokens=%d, output_tokens=%d)",
            elapsed,
            message.usage.input_tokens,
            message.usage.output_tokens,
        )

        # Extract text from the first content block
        if message.content and hasattr(message.content[0], "text"):
            return message.content[0].text
        return ""

    def _parse_response(self, raw: str) -> dict[str, Any]:
        """
        Parse Claude's response as JSON.

        Tries three strategies in order:
          1. Direct json.loads() on the full string.
          2. Extract a ```json ... ``` fenced block.
          3. Extract the first {...} substring.

        Returns a dict with at minimum {"response": <text>, "actions": []}.
        """
        if not raw:
            return {_RESPONSE_KEY: "", _ACTIONS_KEY: []}

        # Strategy 1: direct parse
        try:
            result = json.loads(raw)
            if isinstance(result, dict):
                return self._normalise_parsed(result)
        except json.JSONDecodeError:
            pass

        # Strategy 2: fenced code block
        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if fence_match:
            try:
                result = json.loads(fence_match.group(1))
                if isinstance(result, dict):
                    return self._normalise_parsed(result)
            except json.JSONDecodeError:
                pass

        # Strategy 3: first JSON object in the string
        brace_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if brace_match:
            try:
                result = json.loads(brace_match.group(0))
                if isinstance(result, dict):
                    return self._normalise_parsed(result)
            except json.JSONDecodeError:
                pass

        log.warning(
            "Could not parse Claude response as JSON.  Raw (first 200 chars): %r",
            raw[:200],
        )
        # Return the raw text as the spoken response so the user hears something
        return {_RESPONSE_KEY: raw.strip()[:300], _ACTIONS_KEY: []}

    @staticmethod
    def _normalise_parsed(data: dict[str, Any]) -> dict[str, Any]:
        """Ensure both required keys are present and have the correct types."""
        response = data.get(_RESPONSE_KEY, "")
        if not isinstance(response, str):
            response = str(response)

        actions = data.get(_ACTIONS_KEY, [])
        if not isinstance(actions, list):
            actions = []

        return {_RESPONSE_KEY: response, _ACTIONS_KEY: actions}

    # ------------------------------------------------------------------
    # System prompt construction
    # ------------------------------------------------------------------

    def _build_system_prompt(
        self,
        device_states: list[dict[str, Any]],
        person: str | None = None,
        context: str = "casual",
        time_of_day: str | None = None,
        habit_data: dict[str, Any] | None = None,
    ) -> str:
        """
        Build the full system prompt for Claude.

        When ``AuraPersonality`` is available the personality block is
        generated by it, giving Claude AURA's character, tone, resident-
        specific instructions, and habit context.  The device state snapshot
        and JSON response contract are appended here because they change on
        every request and are not personality concerns.

        Falls back to a minimal static prompt if the personality engine failed
        to load at init time.

        Parameters
        ----------
        device_states:
            List of HA entity state dicts as returned by ``_get_device_states``.
        person:
            Resident ID of the speaker, or ``None`` if unknown.
        context:
            Active context key from ``personality.VALID_CONTEXTS``.
        time_of_day:
            Current time as ``"HH:MM"`` or band name, passed to
            ``AuraPersonality.get_system_prompt()``.
        habit_data:
            Habit tracking snapshot from ``HabitTracker``, or ``None``.

        Returns
        -------
        str
            The fully assembled system prompt string.
        """
        # ── Personality block ──────────────────────────────────────────
        if self._personality is not None:
            personality_block = self._personality.get_system_prompt(
                person=person,
                context=context,
                time_of_day=time_of_day,
                habit_data=habit_data,
            )
        else:
            # Minimal fallback — keeps the pipeline alive if personality.yaml
            # is missing during initial setup or a deployment error.
            personality_block = (
                "You are AURA, the AI assistant for this apartment, "
                "created by OASIS AI Solutions. "
                "You are helpful, warm, witty, and concise — never more than "
                "2-3 sentences. Do not use markdown; your words are read aloud."
            )

        # ── Device state block ─────────────────────────────────────────
        if device_states:
            entity_lines = []
            for state in device_states:
                entity_id = state.get("entity_id", "unknown")
                current_state = state.get("state", "unknown")
                attrs = state.get("attributes", {})
                friendly_name = attrs.get("friendly_name", entity_id)
                entity_lines.append(
                    f"  - {entity_id} ({friendly_name}): {current_state}"
                )
            entities_block = "\n".join(entity_lines)
        else:
            entities_block = (
                "  (Home Assistant is currently unreachable — no live state available)"
            )

        # ── Protocols block ────────────────────────────────────────────
        protocol_lines: list[str] = []
        for name, proto in self._protocols.items():
            description = proto.get("description", "")
            actions_list = proto.get("actions", [])
            actions_str = ", ".join(actions_list)
            protocol_lines.append(
                f'  - "{name}": {description} — [{actions_str}]'
            )
        protocols_block = (
            "\n".join(protocol_lines) if protocol_lines else "  (none configured)"
        )

        # ── Capabilities block ─────────────────────────────────────────
        # The full capabilities map is injected so Claude knows the complete
        # scope of what AURA can do.  This powers accurate answers to "what
        # can you do?", "can you do X?", and category-specific help questions.
        capabilities_block = self._capabilities.get_capabilities_for_prompt()

        # ── JSON contract block ────────────────────────────────────────
        json_contract = """\
RESPONSE FORMAT:
You MUST respond with a single valid JSON object and nothing else — no explanation, no markdown fences. The JSON must have exactly these two keys:

{
  "response": "What you say aloud to the user. Conversational, brief, no markdown.",
  "actions": [
    {
      "domain": "light",
      "service": "turn_on",
      "entity_id": "light.living_room_leds",
      "data": {"brightness_pct": 70, "color_temp": 2700}
    }
  ]
}

RULES:
- The "response" field must always be a non-empty string.
- The "actions" array can be empty if no device changes are needed.
- Only include actions for devices that exist in the current device states list.
- For scene activations, use domain "scene" and service "turn_on".
- For script runs, use domain "script" and service "turn_on".
- If you are unsure how to execute a command, say so in "response" and leave "actions" empty.
- If Home Assistant is unreachable, acknowledge this in your response.
- Never hallucinate entity IDs that are not in the current device states.
- Temperatures for climate entities are in Celsius.
- Be honest if you cannot do something — do not pretend to execute actions you cannot.
- If the user asks "what can you do", "help", "what are your capabilities", or similar,
  walk them through your capabilities conversationally using the CAPABILITIES section below.
  Keep it natural and spoken — no bullet lists, no markdown, no reading a menu aloud.
- If the user asks about a specific feature (e.g. "how do I control lights?"), pull
  relevant examples directly from the CAPABILITIES section and speak them naturally."""

        return (
            f"{personality_block}\n\n"
            f"CURRENT DEVICE STATES:\n{entities_block}\n\n"
            f"KNOWN PROTOCOLS (pre-configured scenes you can activate):\n"
            f"{protocols_block}\n\n"
            f"{capabilities_block}\n\n"
            f"{json_contract}"
        )
