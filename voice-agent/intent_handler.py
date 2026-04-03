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
        "camera",
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
        features: dict[str, Any] | None = None,
    ) -> None:
        if not ha_token:
            log.warning(
                "HA_TOKEN is not set — Home Assistant API calls will fail."
            )
        if not anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY must not be empty.")

        # Feature module instances — keyed by feature name (e.g. "mirror_mode").
        # None values are excluded by the caller, so every entry here is live.
        self._features: dict[str, Any] = features or {}

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

        self._client = anthropic.Anthropic(api_key=anthropic_api_key, timeout=30.0)

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
        self._security_feedback = None  # Reset before action loop
        self._feature_response = None   # Reset before action loop
        if actions:
            log.info("Executing %d action(s)…", len(actions))
            for action in actions:
                if "feature" in action:
                    self._execute_feature_command(action)
                else:
                    self._execute_action(action)
        else:
            log.debug("No actions in Claude response.")

        # If a feature command generated its own response text (e.g. pulse_check
        # check-in, energy oracle brief), use it as the spoken response.
        if self._feature_response:
            response_text = self._feature_response
            log.info("Response overridden by feature output")

        # If a security check blocked an action, override Claude's response
        # so the user hears WHY the action didn't happen
        if self._security_feedback:
            response_text = self._security_feedback
            log.info("Response overridden by security feedback: %r", response_text)

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

        # Webhook dispatch — fires HA webhooks that trigger automations.
        # This bypasses the security check intentionally: the webhooks trigger
        # HA automations that have their own safety conditions, and we do not
        # want the voice security layer blocking protocol activations.
        if domain == "webhook":
            webhook_id = action.get("webhook_id", "")
            if webhook_id:
                try:
                    requests.post(
                        f"http://localhost:5123/{webhook_id}",
                        json={},
                        timeout=5,
                    )
                    log.info("Webhook fired: %s", webhook_id)
                except Exception as exc:  # noqa: BLE001
                    log.error("Failed to fire webhook %s: %s", webhook_id, exc)
            else:
                log.warning("Webhook action missing webhook_id: %s", action)
            return

        # Security check — block or require PIN for sensitive actions
        if self._security:
            status, message = self._security.check_action(domain, service)
            if status == "blocked":
                log.warning("BLOCKED by security policy: %s.%s — %s", domain, service, message)
                self._security_feedback = message
                return
            if status == "pin_required":
                log.warning("PIN required for %s.%s — %s", domain, service, message)
                self._security_feedback = message
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

    def _set_feature_toggle(self, entity_id: str, enabled: bool) -> None:
        """Keep HA input_booleans aligned with voice-enabled feature state."""
        self._execute_action(
            {
                "domain": "input_boolean",
                "service": "turn_on" if enabled else "turn_off",
                "entity_id": entity_id,
            }
        )

    def _execute_feature_command(self, action: dict[str, Any]) -> None:
        """
        Route a feature-specific action returned by Claude to the correct
        feature module instance.

        Feature actions use a ``"feature"`` key instead of ``"domain"``/
        ``"service"``, so the standard ``_execute_action`` path does not apply.

        Supported feature actions and their required keys:

        mirror_mode:
            ``{"feature": "mirror_mode", "mood": "ocean vibes"}``
        aura_drops:
            ``{"feature": "aura_drops", "action": "save",     "name": "...", "person": "..."}``
            ``{"feature": "aura_drops", "action": "activate", "name": "..."}``
            ``{"feature": "aura_drops", "action": "list"}``
        vibe_sync:
            ``{"feature": "vibe_sync", "action": "enable"|"disable"}``
        deja_vu:
            ``{"feature": "deja_vu", "action": "enable"|"disable"}``
        pulse_check:
            ``{"feature": "pulse_check", "action": "check_in", "person": "..."}``
        ghost_dj:
            ``{"feature": "ghost_dj", "action": "suggest"}``
        content_radar:
            ``{"feature": "content_radar", "action": "stats", "person": "..."}``
        energy_oracle:
            ``{"feature": "energy_oracle", "action": "brief", "person": "..."}``

        Unknown feature names and unhandled action values are logged as
        warnings and silently skipped so the pipeline never crashes.
        """
        feature_name: str = action.get("feature", "")
        feature_action: str = action.get("action", "")
        instance = self._features.get(feature_name)

        if instance is None:
            log.warning(
                "Feature %r is not available — skipping action %s",
                feature_name,
                action,
            )
            return

        log.info("Feature command: %s  action=%s", feature_name, feature_action or "(default)")

        try:
            if feature_name == "mirror_mode":
                mood: str = action.get("mood", "ambient")
                result = instance.activate(mood)
                if isinstance(result, str) and result:
                    self._feature_response = result

            elif feature_name == "aura_drops":
                name: str = action.get("name", "")
                person: str = action.get("person", "unknown")
                if feature_action == "save":
                    result = instance.save_drop(name, person)
                    log.info("AuraDrops save result: %s", result)
                    if isinstance(result, str) and result:
                        self._feature_response = result
                elif feature_action == "activate":
                    result = instance.activate_drop(name)
                    log.info("AuraDrops activate result: %s", result)
                    if isinstance(result, str) and result:
                        self._feature_response = result
                elif feature_action == "list":
                    result = instance.list_drops_summary()
                    log.info("AuraDrops list: %s", result)
                    if isinstance(result, str) and result:
                        self._feature_response = result
                else:
                    log.warning("Unknown aura_drops action: %r", feature_action)

            elif feature_name == "vibe_sync":
                if feature_action == "enable":
                    result = instance.enable()
                    self._set_feature_toggle("input_boolean.vibe_sync_enabled", True)
                    instance.poll_and_adjust()
                    log.info("VibeSync enabled: %s", result)
                elif feature_action == "disable":
                    result = instance.disable()
                    self._set_feature_toggle("input_boolean.vibe_sync_enabled", False)
                    log.info("VibeSync disabled: %s", result)
                else:
                    log.warning("Unknown vibe_sync action: %r", feature_action)

            elif feature_name == "deja_vu":
                if feature_action == "enable":
                    result = instance.enable()
                    self._set_feature_toggle("input_boolean.deja_vu_enabled", True)
                    person = action.get("person", "conaugh")
                    prediction = instance.maybe_predict_and_activate(person)
                    log.info("DejaVu enabled: %s prediction=%r", result, prediction)
                elif feature_action == "disable":
                    result = instance.disable()
                    self._set_feature_toggle("input_boolean.deja_vu_enabled", False)
                    log.info("DejaVu disabled: %s", result)
                else:
                    log.warning("Unknown deja_vu action: %r", feature_action)

            elif feature_name == "pulse_check":
                if feature_action == "check_in":
                    person = action.get("person", "conaugh")
                    text = instance.generate_check_in(person)
                    log.info("PulseCheck check-in generated for %s: %r", person, text[:80])
                    if text:
                        self._feature_response = text
                else:
                    log.warning("Unknown pulse_check action: %r", feature_action)

            elif feature_name == "ghost_dj":
                if feature_action == "suggest":
                    suggestion = instance.suggest_music(
                        action.get("context", {}),
                        action.get("person"),
                    )
                    if suggestion:
                        instance.apply_music(suggestion)
                        log.info("GhostDJ suggestion applied.")
                    else:
                        log.info("GhostDJ: no suggestion at this time.")
                else:
                    log.warning("Unknown ghost_dj action: %r", feature_action)

            elif feature_name == "content_radar":
                if feature_action == "stats":
                    person = action.get("person", "conaugh")
                    stats = instance.get_content_stats(person)
                    log.info("ContentRadar stats for %s: %s", person, stats)
                    if isinstance(stats, dict) and stats:
                        # Build a TTS-friendly summary from the stats dict
                        sessions = stats.get("total_sessions", 0)
                        days_since = stats.get("days_since_last_session", 0)
                        avg_len = stats.get("average_session_length", 0.0)
                        mode = stats.get("most_used_mode") or "studio"
                        stats_text = (
                            f"You've had {sessions} content session"
                            f"{'s' if sessions != 1 else ''} in the last 30 days. "
                            f"Last session was {days_since} day"
                            f"{'s' if days_since != 1 else ''} ago. "
                            f"Average session length is {avg_len:.0f} minutes. "
                            f"Most used mode: {mode}."
                        )
                        self._feature_response = stats_text
                    elif isinstance(stats, str) and stats:
                        self._feature_response = stats
                else:
                    log.warning("Unknown content_radar action: %r", feature_action)

            elif feature_name == "social_sonar":
                if feature_action == "detect":
                    detection = instance.detect_social_context()
                    if detection.get("likely_guests"):
                        result = instance.apply_social_mode()
                    else:
                        instance.reset()
                        result = "Social mode reset."
                    log.info("SocialSonar result: %s detection=%s", result, detection)
                elif feature_action == "reset":
                    instance.reset()
                    log.info("SocialSonar reset requested.")
                else:
                    log.warning("Unknown social_sonar action: %r", feature_action)

            elif feature_name == "phantom_presence":
                if feature_action == "generate":
                    hours = int(action.get("hours", 6))
                    schedule = instance.generate_simulation_schedule(hours=hours)
                    script_yaml = instance.create_ha_script(schedule)
                    log.info(
                        "PhantomPresence generated %d scheduled action(s); script size=%d chars",
                        len(schedule),
                        len(script_yaml),
                    )
                elif feature_action == "summary":
                    summary = instance.get_typical_evening()
                    log.info("PhantomPresence summary: %s", summary)
                else:
                    log.warning("Unknown phantom_presence action: %r", feature_action)

            elif feature_name == "energy_oracle":
                if feature_action == "brief":
                    person = action.get("person", "conaugh")
                    brief = instance.generate_weekly_brief(person)
                    log.info("EnergyOracle brief for %s: %r", person, (brief or "")[:80])
                    if brief:
                        self._feature_response = brief
                else:
                    log.warning("Unknown energy_oracle action: %r", feature_action)

            else:
                log.warning("No handler for feature %r — action dropped.", feature_name)

        except Exception as exc:  # noqa: BLE001
            log.error(
                "Error executing feature command %r action=%r: %s",
                feature_name,
                feature_action,
                exc,
                exc_info=True,
            )

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
                domain = entity_id.split(".")[0]

                # Build an attribute suffix so Claude can answer live questions
                # like "what's the temperature?" or "what's playing?" accurately.
                attr_parts: list[str] = []
                if domain == "climate":
                    if "current_temperature" in attrs:
                        attr_parts.append(f"current_temperature: {attrs['current_temperature']}")
                    if "hvac_mode" in attrs:
                        attr_parts.append(f"hvac_mode: {attrs['hvac_mode']}")
                elif domain == "media_player":
                    if "volume_level" in attrs:
                        attr_parts.append(f"volume_level: {attrs['volume_level']}")
                    if "media_title" in attrs:
                        attr_parts.append(f"media_title: {attrs['media_title']}")
                elif domain == "light":
                    if "brightness" in attrs:
                        attr_parts.append(f"brightness: {attrs['brightness']}")
                    if "color_mode" in attrs:
                        attr_parts.append(f"color_mode: {attrs['color_mode']}")

                attr_suffix = f" [{', '.join(attr_parts)}]" if attr_parts else ""
                entity_lines.append(
                    f"  - {entity_id} ({friendly_name}): {current_state}{attr_suffix}"
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
        if protocol_lines:
            protocol_lines.append(
                "\nTo activate any protocol, include this action in the actions array:\n"
                '  {"domain": "webhook", "service": "fire", "webhook_id": "aura_<protocol_name>"}\n'
                'For example, to activate close_down:\n'
                '  {"domain": "webhook", "service": "fire", "webhook_id": "aura_close_down"}\n'
                'For open_up:\n'
                '  {"domain": "webhook", "service": "fire", "webhook_id": "aura_open_up"}'
            )
        protocols_block = (
            "\n".join(protocol_lines) if protocol_lines else "  (none configured)"
        )

        # ── Capabilities block ─────────────────────────────────────────
        # The full capabilities map is injected so Claude knows the complete
        # scope of what AURA can do.  This powers accurate answers to "what
        # can you do?", "can you do X?", and category-specific help questions.
        capabilities_block = self._capabilities.get_capabilities_for_prompt()

        # ── Feature actions block ──────────────────────────────────────
        available_features = list(self._features.keys())
        if available_features:
            feature_lines = [
                "You can also return these special feature actions in the \"actions\" array.",
                "Use the \"feature\" key instead of \"domain\"/\"service\":",
                "",
            ]
            feature_examples: list[str] = []
            if "mirror_mode" in available_features:
                feature_examples.append(
                    '  {"feature": "mirror_mode", "mood": "ocean vibes"}'
                    " — coordinated multi-light color choreography"
                )
            if "aura_drops" in available_features:
                feature_examples += [
                    '  {"feature": "aura_drops", "action": "save", "name": "Chill Mode", "person": "<person>"}'
                    " — snapshot current device state",
                    '  {"feature": "aura_drops", "action": "activate", "name": "Chill Mode"}'
                    " — restore a saved snapshot",
                    '  {"feature": "aura_drops", "action": "list"}'
                    " — list all saved drops",
                ]
            if "vibe_sync" in available_features:
                feature_examples.append(
                    '  {"feature": "vibe_sync", "action": "enable"}'
                    " — run one music-reactive lighting adjustment"
                )
            if "deja_vu" in available_features:
                feature_examples.append(
                    '  {"feature": "deja_vu", "action": "enable"}'
                    " — run a predictive scene activation check"
                )
            if "pulse_check" in available_features:
                feature_examples.append(
                    '  {"feature": "pulse_check", "action": "check_in", "person": "<person>"}'
                    " — generate an accountability check-in"
                )
            if "ghost_dj" in available_features:
                feature_examples.append(
                    '  {"feature": "ghost_dj", "action": "suggest"}'
                    " — auto-select and play context-aware music"
                )
            if "content_radar" in available_features:
                feature_examples.append(
                    '  {"feature": "content_radar", "action": "stats", "person": "<person>"}'
                    " — content creation session statistics"
                )
            if "social_sonar" in available_features:
                feature_examples.append(
                    '  {"feature": "social_sonar", "action": "detect"}'
                    " â€” detect guests and subtly adjust the environment"
                )
            if "phantom_presence" in available_features:
                feature_examples.append(
                    '  {"feature": "phantom_presence", "action": "generate", "hours": 6}'
                    " â€” generate an away-mode simulation schedule"
                )
            if "energy_oracle" in available_features:
                feature_examples.append(
                    '  {"feature": "energy_oracle", "action": "brief", "person": "<person>"}'
                    " — weekly intelligence brief"
                )
            feature_lines += feature_examples
            feature_actions_block = "\n".join(feature_lines)
        else:
            feature_actions_block = ""

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
- ONLY include actions for devices that exist in the CURRENT DEVICE STATES list above. If a device is not listed, you DO NOT have access to it. Period.
- If the user asks you to control something that is not in the device states list (e.g. thermostat, blinds, lock, camera), be honest: "I don't have access to a thermostat right now. You'd need to add one to the system first." Do NOT pretend to control devices that aren't connected.
- If the device states list says "(Home Assistant is currently unreachable)", tell the user: "I can't reach Home Assistant right now, so I can't control any devices. I can still chat though."
- For scene activations, use domain "scene" and service "turn_on".
- For script runs, use domain "script" and service "turn_on".
- If you are unsure how to execute a command, say so in "response" and leave "actions" empty. Never guess.
- Never hallucinate entity IDs. If it is not in the device states list, it does not exist.
- The CAPABILITIES section describes what AURA supports in general. The DEVICE STATES list is the ground truth for what is physically connected RIGHT NOW. If a capability references a device type that is not in the device states (e.g., capabilities mention thermostat but no climate entity exists), tell the user: "AURA supports thermostat control, but there's no thermostat connected to the system yet."
- Temperatures for climate entities are in Celsius.
- Be honest and direct if you cannot do something. Say "I don't have access to that" or "That device isn't connected yet." Never pretend or make up actions.
- If the user asks "what can you do", "help", "what are your capabilities", or similar,
  walk them through your capabilities conversationally using the CAPABILITIES section below.
  Keep it natural and spoken — no bullet lists, no markdown, no reading a menu aloud.
- If the user asks about a specific feature (e.g. "how do I control lights?"), pull
  relevant examples directly from the CAPABILITIES section and speak them naturally."""

        feature_section = (
            f"FEATURE ACTIONS (use \"feature\" key instead of \"domain\"/\"service\"):\n"
            f"{feature_actions_block}\n\n"
            if feature_actions_block
            else ""
        )

        return (
            f"{personality_block}\n\n"
            f"CURRENT DEVICE STATES:\n{entities_block}\n\n"
            f"KNOWN PROTOCOLS (pre-configured scenes you can activate):\n"
            f"{protocols_block}\n\n"
            f"{capabilities_block}\n\n"
            f"{feature_section}"
            f"{json_contract}"
        )
