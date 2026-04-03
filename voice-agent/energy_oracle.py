"""
AURA Energy Oracle — Weekly Intelligence Brief
===============================================
Every Sunday morning AURA delivers a comprehensive spoken briefing covering
the apartment's full week.  The Oracle pulls data from every layer of the
system — habits, automations, content sessions, device usage, and energy
consumption — synthesises it into structured data, then asks Claude to write
a conversational 60–90 second briefing that actually sounds like AURA.

Architecture
------------
EnergyOracle is a read-only aggregator — it never writes to any database or
calls HA services.  Its sole output is text for TTS and structured data for
the dashboard.

Data sources:
  - HabitTracker.get_weekly_report()  — gym/meals/sleep/work streaks
  - PatternEngine.get_suggestions()   — pending automation improvements
  - ContentRadar.get_content_stats()  — content creation sessions
  - HA REST /api/states               — device snapshots + energy sensor

All sources are queried in parallel (via threading) so the total latency
is bounded by the slowest source, not their sum.

Claude prompt design
--------------------
The system prompt gives Claude the full personality context (same tone as the
voice agent) plus a structured JSON data blob.  Claude is instructed to write
a spoken brief of 3–5 paragraphs, naturally weaving in the numbers without
reading them out mechanically.  The brief must:
  1. Open with a punchy one-liner (not "Good morning, here is your weekly report").
  2. Cover habits: celebrate streaks, acknowledge misses without lecturing.
  3. Mention automation insights if suggestions exist.
  4. Reference content stats.
  5. Close with one forward-looking motivational line and offer to share
     the automation suggestions in detail if the resident wants.

Design decisions
----------------
- Claude max_tokens is set to 400 (≈ 90 seconds of speech at ~270 wpm average).
  The caller should pass the returned text directly to TTS.
- All data sources are wrapped in try/except so a single failing source
  (e.g. HA unreachable, ContentRadar DB locked) degrades the brief gracefully
  rather than crashing the entire Sunday routine.
- EnergyOracle does not call TTS or play audio — that is the voice agent's job.
  The caller (aura_voice.py or the HA webhook handler) is responsible for
  piping the returned text to ElevenLabs.

Usage::

    from energy_oracle import EnergyOracle
    oracle = EnergyOracle(
        ha_url=os.environ["HA_URL"],
        ha_token=os.environ["HA_TOKEN"],
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        pattern_engine=engine,
        habit_tracker=tracker,
        content_radar=radar,
    )
    brief_text = oracle.generate_weekly_brief("conaugh")
    tts.speak(brief_text)
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional, Protocol

import requests

log = logging.getLogger("aura.energy_oracle")

# ---------------------------------------------------------------------------
# Dependency protocols — loose coupling
# ---------------------------------------------------------------------------


class _HabitTrackerProtocol(Protocol):
    def get_weekly_report(self, person: str) -> Any:
        ...

    def format_weekly_summary(self, person: str) -> str:
        ...


class _PatternEngineProtocol(Protocol):
    def get_suggestions(self) -> list[Any]:
        ...


class _ContentRadarProtocol(Protocol):
    def get_content_stats(self, person: str, days: int = 30) -> dict[str, Any]:
        ...

    def suggest_content_time(self, person: str) -> dict[str, Any]:
        ...


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Claude model used for brief generation.
_CLAUDE_MODEL = "claude-sonnet-4-6"

# Token budget for the weekly brief.  ~400 tokens ≈ 90 seconds of speech.
_BRIEF_MAX_TOKENS = 400

# Claude temperature for the brief — slightly higher than intent processing
# to allow more natural, varied language.
_BRIEF_TEMPERATURE = 0.6


# ---------------------------------------------------------------------------
# EnergyOracle
# ---------------------------------------------------------------------------


class EnergyOracle:
    """
    Aggregates all AURA data sources and generates a weekly spoken intelligence
    brief via Claude.

    Parameters
    ----------
    ha_url:
        Base URL of the Home Assistant instance.
    ha_token:
        Long-lived HA access token.
    anthropic_api_key:
        API key for the Anthropic Claude API.
    pattern_engine:
        PatternEngine instance from the learning module.
    habit_tracker:
        HabitTracker instance from the learning module.
    content_radar:
        ContentRadar instance from the voice-agent module.
    """

    def __init__(
        self,
        ha_url: str,
        ha_token: str,
        anthropic_api_key: str,
        pattern_engine: _PatternEngineProtocol,
        habit_tracker: Optional[_HabitTrackerProtocol] = None,
        content_radar: Optional[_ContentRadarProtocol] = None,
        claude_model: str = _CLAUDE_MODEL,
    ) -> None:
        if not ha_token:
            log.warning("HA_TOKEN not set — HA device data will be unavailable.")
        if not anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY must not be empty.")

        self._ha_url = ha_url.rstrip("/")
        self._ha_headers: dict[str, str] = {
            "Authorization": f"Bearer {ha_token}",
            "Content-Type": "application/json",
        }
        self._anthropic_api_key = anthropic_api_key
        self._pattern_engine = pattern_engine
        self._habit_tracker = habit_tracker
        self._content_radar = content_radar
        self._claude_model = claude_model

        import anthropic  # type: ignore[import-untyped]

        self._claude = anthropic.Anthropic(api_key=anthropic_api_key, timeout=30.0)
        log.info("EnergyOracle initialised (model: %s).", claude_model)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_weekly_brief(self, person: str) -> str:
        """
        Generate a conversational 60–90 second spoken weekly briefing for
        ``person`` by aggregating all data sources and calling Claude.

        Parameters
        ----------
        person:
            Resident ID: ``"conaugh"`` or ``"adon"``.

        Returns
        -------
        str
            Plain text briefing ready for TTS.  Never contains markdown.
            Returns a safe fallback string on any error.
        """
        log.info("Generating weekly brief for %s…", person)

        data = self.get_weekly_data(person)

        system_prompt = self._build_brief_system_prompt(person)
        user_message = (
            f"Generate the weekly brief for {person.capitalize()} "
            f"using this data:\n\n{json.dumps(data, indent=2, default=str)}"
        )

        try:
            message = self._claude.messages.create(
                model=self._claude_model,
                max_tokens=_BRIEF_MAX_TOKENS,
                temperature=_BRIEF_TEMPERATURE,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            brief = message.content[0].text.strip() if message.content else ""
            if not brief:
                raise ValueError("Claude returned an empty response.")
            log.info(
                "Weekly brief generated for %s (%d chars).",
                person,
                len(brief),
            )
            return brief

        except Exception as exc:  # noqa: BLE001
            log.error(
                "Failed to generate weekly brief via Claude: %s", exc, exc_info=True
            )
            return self._fallback_brief(person, data)

    def get_weekly_data(self, person: str) -> dict[str, Any]:
        """
        Aggregate data from all sources into a single structured dict.

        All sources are queried concurrently via threads.  Individual source
        failures are caught and reported as ``{"error": "<message>"}`` in the
        corresponding key so the brief degrades gracefully.

        Returns
        -------
        dict with keys:
          - ``person``          (str)
          - ``week_ending``     (str)    — ISO date
          - ``habit_summary``   (dict)   — from HabitTracker
          - ``content_stats``   (dict)   — from ContentRadar
          - ``suggestions``     (list)   — from PatternEngine
          - ``device_snapshot`` (dict)   — from HA REST API
          - ``generated_at``    (str)    — UTC ISO timestamp
        """
        result: dict[str, Any] = {
            "person": person,
            "week_ending": datetime.now(timezone.utc).date().isoformat(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Gather from all sources concurrently
        targets: dict[str, Any] = {}
        errors: dict[str, str] = {}
        lock = threading.Lock()

        def _fetch(key: str, fn: Any, *args: Any, **kwargs: Any) -> None:
            try:
                value = fn(*args, **kwargs)
                with lock:
                    targets[key] = value
            except Exception as exc:  # noqa: BLE001
                log.warning("Data source %r failed: %s", key, exc)
                with lock:
                    errors[key] = str(exc)

        threads = [
            threading.Thread(
                target=_fetch,
                args=("habit_summary", self._get_habit_summary, person),
                daemon=True,
            ),
            threading.Thread(
                target=_fetch,
                args=("suggestions", self.get_automation_suggestions),
                daemon=True,
            ),
            threading.Thread(
                target=_fetch,
                args=("device_snapshot", self._get_device_snapshot),
                daemon=True,
            ),
        ]

        if self._content_radar is not None:
            threads.append(
                threading.Thread(
                    target=_fetch,
                    args=("content_stats", self._content_radar.get_content_stats, person),
                    kwargs={"days": 7},
                    daemon=True,
                )
            )

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        result.update(targets)
        if errors:
            result["source_errors"] = errors

        return result

    def get_automation_suggestions(self) -> list[dict[str, Any]]:
        """
        Pull all pending automation suggestions from PatternEngine and format
        them as a list of human-readable dicts for inclusion in the brief.

        Returns
        -------
        list[dict]
            Each entry has: ``automation_id``, ``suggestion_type``,
            ``current_value``, ``suggested_value``, ``reason``.
        """
        try:
            raw = self._pattern_engine.get_suggestions()
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to fetch automation suggestions: %s", exc)
            return []

        formatted: list[dict[str, Any]] = []
        for suggestion in raw:
            formatted.append(
                {
                    "automation_id": suggestion.automation_id,
                    "suggestion_type": suggestion.suggestion_type,
                    "current_value": suggestion.current_value,
                    "suggested_value": suggestion.suggested_value,
                    "reason": suggestion.reason,
                }
            )

        log.debug("Fetched %d pending automation suggestions.", len(formatted))
        return formatted

    # ------------------------------------------------------------------
    # Private — data fetchers
    # ------------------------------------------------------------------

    def _get_habit_summary(self, person: str) -> dict[str, Any]:
        """
        Build a structured habit summary from the HabitTracker weekly report.
        """
        if self._habit_tracker is None:
            log.debug("HabitTracker not available — returning empty habit summary.")
            return {
                "average_completion_pct": 0.0,
                "streaks": {},
                "best_habit": None,
                "worst_habit": None,
                "plain_summary": "No habit data available.",
            }

        report = self._habit_tracker.get_weekly_report(person)
        plain_summary = self._habit_tracker.format_weekly_summary(person)

        streaks: dict[str, int] = report.streaks if hasattr(report, "streaks") else {}
        avg_completion = (
            report.average_completion if hasattr(report, "average_completion") else 0.0
        )
        best_habit = getattr(report, "best_habit", None)
        worst_habit = getattr(report, "worst_habit", None)

        return {
            "average_completion_pct": round(avg_completion * 100, 1),
            "streaks": streaks,
            "best_habit": best_habit,
            "worst_habit": worst_habit,
            "plain_summary": plain_summary,
        }

    def _get_device_snapshot(self) -> dict[str, Any]:
        """
        Fetch a minimal device snapshot from HA: thermostat, energy, and
        scene/mode activation counters.
        """
        entities_to_fetch = [
            "climate.thermostat",
            "sensor.total_energy_today",
            "counter.studio_mode_activations",
            "counter.content_mode_activations",
            "counter.party_mode_activations",
            "counter.gym_reminder_acknowledged",
        ]

        snapshot: dict[str, Any] = {}
        for entity_id in entities_to_fetch:
            state = self._get_state(entity_id)
            if state != "unavailable":
                snapshot[entity_id.split(".")[-1]] = state

        return snapshot

    def _get_state(self, entity_id: str) -> str:
        """Return the HA state string for ``entity_id``, or 'unavailable'."""
        url = f"{self._ha_url}/api/states/{entity_id}"
        try:
            resp = requests.get(url, headers=self._ha_headers, timeout=5)
            if resp.status_code == 200:
                return resp.json().get("state", "unavailable")
            return "unavailable"
        except requests.exceptions.RequestException:
            return "unavailable"

    # ------------------------------------------------------------------
    # Private — prompt and fallback
    # ------------------------------------------------------------------

    def _build_brief_system_prompt(self, person: str) -> str:
        """
        Build the system prompt for Claude's weekly brief generation.
        """
        display_name = person.capitalize()
        return (
            f"You are AURA, the AI apartment assistant for {display_name}. "
            "You were created by OASIS AI Solutions. "
            "Your voice is witty, warm, real — you're the smart homie who runs "
            "the apartment. You use natural slang but keep it professional enough "
            "to be taken seriously. You celebrate wins loudly, acknowledge misses "
            "briefly without lecturing, and always end on a forward-looking note.\n\n"
            "TASK: Generate a weekly spoken briefing. This will be read aloud by "
            "ElevenLabs TTS — no markdown, no bullet points, no headers. "
            "Write continuous conversational paragraphs only.\n\n"
            "LENGTH: 3–5 paragraphs. Target 60–90 seconds of speech "
            "(approximately 270–400 words).\n\n"
            "STRUCTURE (follow loosely, don't be mechanical):\n"
            "1. Punchy opening line — NOT 'Good morning, here is your weekly report'.\n"
            "2. Habit recap: celebrate the best streak, briefly mention what needs work.\n"
            "3. Content creation recap: how many sessions, best mode, any patterns.\n"
            "4. Automation insights: if suggestions exist, tease them (1 sentence).\n"
            "5. Forward-looking close: one motivational line + offer to go deeper on "
            "automation suggestions if the resident wants.\n\n"
            "RULES:\n"
            "- Never use markdown, asterisks, bullet points, or numbered lists.\n"
            "- Reference numbers naturally in speech ('six out of seven' not '6/7').\n"
            "- Be specific — reference actual habit names and session counts.\n"
            "- Keep energy high but not fake-hype. Real talk, real data.\n"
            "- If a data source is missing, skip that section naturally.\n"
            "- Return ONLY the spoken brief text. Nothing else."
        )

    def _fallback_brief(self, person: str, data: dict[str, Any]) -> str:
        """
        Generate a minimal fallback brief from raw data without Claude,
        in case the API call fails.
        """
        display_name = person.capitalize()
        habit_data = data.get("habit_summary", {})
        avg_pct = habit_data.get("average_completion_pct", 0)
        content_data = data.get("content_stats", {})
        sessions = content_data.get("total_sessions", 0)
        suggestions = data.get("suggestions", [])

        parts: list[str] = [
            f"Alright {display_name}, here's the weekly.",
            f"Habit completion averaged {avg_pct:.0f}% this week.",
        ]
        if sessions > 0:
            parts.append(f"You got {sessions} content session{'s' if sessions != 1 else ''} in.")
        if suggestions:
            parts.append(
                f"I've got {len(suggestions)} automation suggestion{'s' if len(suggestions) != 1 else ''} "
                "ready when you want to review them."
            )
        parts.append("Keep building.")

        return "  ".join(parts)
