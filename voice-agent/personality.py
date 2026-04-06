"""
AURA Personality Engine
=======================
Defines AURA's character and governs how it speaks.

Loads ``personality.yaml`` from the same directory, then exposes methods for
generating the Claude system prompt, contextual greetings, and accountability
nudges.  Also provides lightweight speech-pattern logging so AURA can
gradually mirror the slang and phrasing each resident uses.

Design decisions
----------------
- Configuration is data-driven via ``personality.yaml`` so personality can be
  tuned without touching Python.
- System prompts are assembled as plain text — no markdown, because the
  response is read aloud by ElevenLabs.
- ``log_speech_pattern`` appends to an append-only JSONL file rather than a
  database so it has zero runtime dependencies beyond stdlib.
- All public methods accept ``person`` as a str key (``"conaugh"`` /
  ``"adon"``) or ``None`` when the speaker is unknown.

Usage::

    personality = AuraPersonality()
    prompt = personality.get_system_prompt(
        person="conaugh",
        context="working",
        time_of_day="afternoon",
    )
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger("aura.personality")

# Directory this file lives in — used to resolve sibling files.
_HERE = Path(__file__).resolve().parent

# Path to the personality configuration file.
_PERSONALITY_YAML = _HERE / "personality.yaml"

# Path to the speech pattern log (JSONL, one entry per logged phrase).
# Written to the project-level data/ directory (one level above voice-agent/)
# so the file is shared across all components and survives voice-agent redeploys.
_SPEECH_PATTERN_LOG = _HERE.parent / "data" / "speech_patterns.jsonl"

# Valid context keys (matches the keys in personality.yaml ``contexts``).
VALID_CONTEXTS = frozenset(
    {
        "casual",
        "working",
        "creating_content",
        "waking_up",
        "going_to_bed",
        "party",
        "guest",
        "accountability_check",
    }
)

# Time-of-day bands used by get_greeting and get_system_prompt.
# Each tuple is (start_hour_inclusive, end_hour_exclusive, band_name).
_TIME_BANDS: list[tuple[int, int, str]] = [
    (5, 12, "morning"),
    (12, 18, "afternoon"),
    (18, 22, "evening"),
    (22, 24, "late_night"),
    (0, 5, "late_night"),
]


def _hour_to_band(hour: int) -> str:
    """Return the time-of-day band name for the given 24-hour clock hour."""
    for start, end, band in _TIME_BANDS:
        if start <= hour < end:
            return band
    return "morning"  # fallback — should never be reached


class AuraPersonality:
    """
    Manages AURA's character, tone, and per-resident speech adaptation.

    Parameters
    ----------
    yaml_path:
        Path to ``personality.yaml``.  Defaults to the sibling file in the
        same directory as this module.

    Raises
    ------
    FileNotFoundError
        If ``personality.yaml`` cannot be found at the given path.
    ValueError
        If ``personality.yaml`` is missing required top-level sections.
    """

    def __init__(self, yaml_path: Path = _PERSONALITY_YAML) -> None:
        if not yaml_path.exists():
            raise FileNotFoundError(
                f"personality.yaml not found at {yaml_path}. "
                "Ensure it is in the same directory as personality.py."
            )

        with yaml_path.open("r", encoding="utf-8") as fh:
            self._cfg: dict[str, Any] = yaml.safe_load(fh)

        self._validate_config()
        log.info("AuraPersonality loaded from %s", yaml_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_system_prompt(
        self,
        person: str | None,
        context: str,
        time_of_day: str | None = None,
        habit_data: dict[str, Any] | None = None,
    ) -> str:
        """
        Build the full system prompt to pass to the Claude API.

        The prompt describes AURA's identity, the current context, resident-
        specific instructions, habit/accountability context, and the phrases
        AURA should avoid.

        Parameters
        ----------
        person:
            Resident key (``"conaugh"`` / ``"adon"``) or ``None`` if unknown.
        context:
            One of the keys in ``VALID_CONTEXTS``.  Falls back to ``"casual"``
            if an unrecognised value is supplied.
        time_of_day:
            ISO-format time string (``"HH:MM"``) or a pre-resolved band name
            (``"morning"``, ``"afternoon"``, etc.).  If ``None``, resolved from
            the current system time.
        habit_data:
            Optional dict of habit tracking data returned by ``HabitTracker``.
            Included verbatim so Claude can reference streaks and misses.

        Returns
        -------
        str
            The fully assembled system prompt, ready to pass to the Claude API.
        """
        if context not in VALID_CONTEXTS:
            log.warning(
                "Unknown context %r — falling back to 'casual'.", context
            )
            context = "casual"

        band = self._resolve_time_band(time_of_day)
        identity_block = self._build_identity_block()
        context_block = self._build_context_block(context, band)
        resident_block = self._build_resident_block(person)
        habit_block = self._build_habit_block(person, habit_data)
        avoid_block = self._build_avoid_block()
        speech_pattern_block = self._build_speech_pattern_block(person)

        return "\n\n".join(
            block
            for block in [
                identity_block,
                context_block,
                resident_block,
                habit_block,
                speech_pattern_block,
                avoid_block,
            ]
            if block.strip()
        )

    def get_greeting(
        self,
        person: str | None,
        time_of_day: str | None = None,
        returning_home: bool = False,
    ) -> str:
        """
        Generate a contextual greeting for a resident.

        Returns a template string with ``{name}`` already substituted.  The
        template is intended as a prompt seed — callers can pass it to
        ``IntentHandler`` for Claude to enrich before speaking.

        Parameters
        ----------
        person:
            Resident key or ``None``.  Falls back to ``"bro"`` when unknown.
        time_of_day:
            ISO-format time string or band name.  Defaults to current time.
        returning_home:
            If ``True``, use the "returning home" variant of the greeting.

        Returns
        -------
        str
            A greeting string appropriate to the time and situation.

        Examples
        --------
        Morning standard::

            "Yo Conaugh, rise and shine bro. Let's get this bread today."

        Evening returning::

            "Welcome back Adon! How was the grind?"

        Late-night::

            "Aye, it's getting late Conaugh. You tryna wrap up or we
            grinding all night?"
        """
        name = self._resolve_display_name(person)
        band = self._resolve_time_band(time_of_day)
        templates: dict[str, dict[str, str]] = self._cfg.get(
            "greeting_templates", {}
        )

        band_templates = templates.get(band, {})
        variant = "returning" if returning_home else "standard"
        template = band_templates.get(variant, "Hey {name}, what's good?")

        return template.format(name=name)

    def get_accountability_message(
        self,
        person: str | None,
        habit_data: dict[str, Any],
    ) -> str:
        """
        Generate an accountability nudge based on current habit data.

        Tone escalates based on ``accountability.gentle_reminder``,
        ``accountability.direct_reminder``, and ``accountability.tough_love``
        thresholds configured in ``personality.yaml``.  Always closes with
        positive encouragement per ``accountability.always_end_positive``.

        Parameters
        ----------
        person:
            Resident key or ``None``.
        habit_data:
            Dict returned by ``HabitTracker`` containing streak and miss info.
            Expected keys (all optional — method degrades gracefully):
              - ``habit``       (str)  — habit name, e.g. ``"gym"``
              - ``streak``      (int)  — consecutive days completed
              - ``days_missed`` (int)  — consecutive days missed

        Returns
        -------
        str
            A plain-English accountability message ready to pass to TTS.

        Examples
        --------
        Two days missed::

            "Bro, two days no gym. We said we're locking in this year.
            Tomorrow morning, no excuses."

        Five-day streak::

            "5 days straight at the gym, Conaugh. You're different.
            Keep that energy."
        """
        name = self._resolve_display_name(person)
        habit = habit_data.get("habit", "that habit")
        streak: int = int(habit_data.get("streak", 0))
        days_missed: int = int(habit_data.get("days_missed", 0))

        acct_cfg: dict[str, Any] = self._cfg.get("accountability", {})
        gentle_threshold: int = int(acct_cfg.get("gentle_reminder", 1))
        direct_threshold: int = int(acct_cfg.get("direct_reminder", 2))
        tough_threshold: int = int(acct_cfg.get("tough_love", 4))

        # Streak celebration takes priority over miss messages.
        if streak > 0:
            return self._build_streak_message(name, habit, streak)

        if days_missed <= 0:
            return f"You're on track with {habit}, {name}. Keep it moving."

        # Escalating tone based on days missed.
        if days_missed >= tough_threshold:
            msg = (
                f"Real talk {name} — {days_missed} days off {habit}. "
                f"You said this was non-negotiable. "
                f"No more delays. Tomorrow is the day."
            )
        elif days_missed >= direct_threshold:
            msg = (
                f"Two days no {habit}, {name}. "
                f"What's going on? "
                f"We said we're locking in this year. Tomorrow morning, no excuses."
            )
        elif days_missed >= gentle_threshold:
            msg = (
                f"Missed {habit} today, {name}. "
                f"We going tomorrow?"
            )
        else:
            msg = f"Hey {name}, don't forget {habit} today."

        # Always end positive if configured.
        if acct_cfg.get("always_end_positive", True):
            msg += " You got this."

        return msg

    def log_speech_pattern(self, person: str, phrase: str) -> None:
        """
        Record a phrase or slang term used by a resident so AURA can adopt it.

        Appends a JSONL entry to ``data/speech_patterns.jsonl``.  The file is
        created if it does not exist.  Failures are logged and swallowed so a
        disk issue never disrupts the voice pipeline.

        Parameters
        ----------
        person:
            Resident key (``"conaugh"`` / ``"adon"``).
        phrase:
            The phrase, word, or slang term to record.  Whitespace is stripped.

        Notes
        -----
        The patterns file is read back by ``get_system_prompt`` to populate a
        "mirroring" section in Claude's context.  Claude is instructed to
        naturally incorporate the phrases when talking to that person.
        """
        phrase = phrase.strip()
        if not phrase:
            return

        entry: dict[str, str] = {
            "person": person.lower(),
            "phrase": phrase,
            "logged_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            _SPEECH_PATTERN_LOG.parent.mkdir(parents=True, exist_ok=True)
            with _SPEECH_PATTERN_LOG.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
            log.debug("Speech pattern logged for %s: %r", person, phrase)
        except OSError as exc:
            log.warning("Could not write speech pattern log: %s", exc)
            return

        # Keep the log bounded at 500 entries to prevent unbounded disk growth.
        # Uses atomic write (temp file + rename) to prevent corruption on power loss.
        try:
            lines = _SPEECH_PATTERN_LOG.read_text(encoding="utf-8").strip().split("\n")
            if len(lines) > 500:
                import tempfile
                truncated = "\n".join(lines[-500:]) + "\n"
                tmp_fd, tmp_path = tempfile.mkstemp(
                    dir=str(_SPEECH_PATTERN_LOG.parent), suffix=".tmp"
                )
                try:
                    with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmp_fh:
                        tmp_fh.write(truncated)
                    Path(tmp_path).replace(_SPEECH_PATTERN_LOG)
                except Exception:
                    Path(tmp_path).unlink(missing_ok=True)
                    raise
        except Exception:  # noqa: BLE001 — truncation failure is non-fatal
            pass

    # ------------------------------------------------------------------
    # Internal helpers — system prompt construction
    # ------------------------------------------------------------------

    def _build_identity_block(self) -> str:
        """Return the AURA identity and core-traits block."""
        identity: dict[str, str] = self._cfg.get("identity", {})
        traits: list[str] = self._cfg.get("core_traits", [])
        voice: dict[str, Any] = self._cfg.get("voice", {})

        name = identity.get("full_name", "AURA by OASIS")
        role = identity.get("role", "AI apartment assistant")
        created_by = identity.get("created_by", "OASIS AI Solutions")
        tone = voice.get("tone", "casual-professional")
        traits_str = ", ".join(traits) if traits else "witty, friendly, direct"

        return (
            f"You are {name}, created by {created_by}.\n"
            f"Your role: {role}.\n"
            f"Core traits: {traits_str}.\n"
            f"Tone: {tone}.\n"
            "You are the smart homie who runs the apartment — witty, real, "
            "funny, and reliable. You use slang naturally, learn how the "
            "residents talk, and adapt. You are never robotic, never overly "
            "formal, and never passive-aggressive. Keep responses brief — "
            "2-3 sentences max unless detail is specifically needed. "
            "Do not use markdown; your words are read aloud."
        )

    def _build_context_block(self, context: str, band: str) -> str:
        """Return the active context and time-of-day guidance block."""
        contexts: dict[str, Any] = self._cfg.get("contexts", {})
        ctx: dict[str, Any] = contexts.get(context, {})

        energy = ctx.get("energy", "relaxed")
        formality = ctx.get("formality", "low")
        humor = ctx.get("humor_level", "medium")
        description = ctx.get("description", "")
        example = ctx.get("example", "")

        lines = [
            f"CURRENT CONTEXT: {context.upper().replace('_', ' ')}",
            f"Time of day: {band}",
            f"Energy level: {energy} | Formality: {formality} | Humor: {humor}",
        ]
        if description:
            lines.append(f"Guidance: {description}")
        if example:
            lines.append(f'Example response style: "{example}"')

        return "\n".join(lines)

    def _build_resident_block(self, person: str | None) -> str:
        """Return resident-specific instructions, or generic instructions if unknown."""
        if person is None:
            return (
                "RESIDENT: Unknown — a guest or unrecognised voice.\n"
                "Be friendly and helpful. Do not reference personal habits or streaks."
            )

        residents: dict[str, Any] = self._cfg.get("residents", {})
        resident: dict[str, Any] = residents.get(person.lower(), {})

        if not resident:
            return (
                f"RESIDENT: {person} (no profile found).\n"
                "Be friendly and helpful."
            )

        nickname = resident.get("nickname", person.capitalize())
        alt_names: list[str] = resident.get("alt_names", [])
        role = resident.get("role", "")
        areas: list[str] = resident.get("accountability_areas", [])

        lines = [
            f"RESIDENT: {nickname}",
            f"Their role at OASIS: {role}." if role else "",
            f"Address them as '{nickname}' — or mix in: {', '.join(alt_names)}."
            if alt_names
            else "",
            f"Accountability focus areas: {', '.join(areas)}." if areas else "",
        ]
        return "\n".join(line for line in lines if line)

    def _build_habit_block(
        self,
        person: str | None,
        habit_data: dict[str, Any] | None,
    ) -> str:
        """
        Return a habit context block so Claude can reference streaks and
        misses naturally when they come up in conversation.
        """
        if not habit_data:
            return ""

        lines = ["HABIT & ACCOUNTABILITY CONTEXT:"]
        for habit_name, info in habit_data.items():
            if not isinstance(info, dict):
                continue
            streak = info.get("streak", 0)
            missed = info.get("days_missed", 0)
            if streak > 0:
                lines.append(
                    f"  {habit_name}: {streak}-day streak — celebrate this."
                )
            elif missed > 0:
                lines.append(
                    f"  {habit_name}: {missed} day(s) missed — address if relevant."
                )
            else:
                lines.append(f"  {habit_name}: on track.")

        if len(lines) == 1:
            return ""

        lines.append(
            "Reference these naturally when the topic arises — "
            "do not lecture unprompted."
        )
        return "\n".join(lines)

    def _build_avoid_block(self) -> str:
        """Return the list of phrases and patterns AURA must never use."""
        voice: dict[str, Any] = self._cfg.get("voice", {})
        avoid: list[str] = voice.get("avoid", [])

        if not avoid:
            return ""

        formatted = "\n".join(f'  - "{item}"' for item in avoid)
        return f"NEVER say or imply:\n{formatted}"

    def _build_speech_pattern_block(self, person: str | None) -> str:
        """
        Return a block of speech patterns AURA has logged for this resident.

        Reads from the JSONL log file and extracts up to 20 recent phrases for
        the given person.  Returns an empty string if no patterns exist yet or
        if the file cannot be read.
        """
        if person is None:
            return ""

        if not _SPEECH_PATTERN_LOG.exists():
            return ""

        patterns: list[str] = []
        try:
            with _SPEECH_PATTERN_LOG.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry: dict[str, str] = json.loads(line)
                        if entry.get("person", "").lower() == person.lower():
                            patterns.append(entry["phrase"])
                    except (json.JSONDecodeError, KeyError):
                        continue
        except OSError as exc:
            log.warning("Could not read speech pattern log: %s", exc)
            return ""

        # Keep the most recent 20 unique phrases to stay concise.
        seen: set[str] = set()
        unique_recent: list[str] = []
        for phrase in reversed(patterns):
            if phrase not in seen:
                seen.add(phrase)
                unique_recent.append(phrase)
            if len(unique_recent) >= 20:
                break

        if not unique_recent:
            return ""

        phrases_str = ", ".join(f'"{p}"' for p in reversed(unique_recent))
        return (
            f"SPEECH PATTERNS — {person.capitalize()} uses these words/phrases "
            f"naturally. Mirror their energy without forcing it:\n  {phrases_str}"
        )

    # ------------------------------------------------------------------
    # Internal helpers — accountability messages
    # ------------------------------------------------------------------

    def _build_streak_message(self, name: str, habit: str, streak: int) -> str:
        """Return a streak celebration message, escalating at milestones."""
        milestones: list[dict[str, Any]] = self._cfg.get(
            "accountability", {}
        ).get("streak_milestones", [])

        # Find the highest milestone the streak has hit.
        matched_milestone: str = ""
        for milestone in sorted(
            milestones, key=lambda m: int(m.get("days", 0)), reverse=True
        ):
            if streak >= int(milestone.get("days", 0)):
                matched_milestone = milestone.get("message", "")
                break

        if matched_milestone:
            return f"{streak} days straight on {habit}, {name}. {matched_milestone}"

        return (
            f"{streak} day{'s' if streak != 1 else ''} straight on {habit}, "
            f"{name}. You're different. Keep that energy."
        )

    # ------------------------------------------------------------------
    # Internal helpers — config resolution
    # ------------------------------------------------------------------

    def _resolve_display_name(self, person: str | None) -> str:
        """Return the display name for a person key, or 'bro' if unknown."""
        if person is None:
            return "bro"
        residents: dict[str, Any] = self._cfg.get("residents", {})
        resident = residents.get(person.lower(), {})
        return resident.get("nickname", person.capitalize())

    def _resolve_time_band(self, time_of_day: str | None) -> str:
        """
        Resolve a time value to a band name.

        Accepts:
          - ``None``  → current system time
          - A band name (``"morning"``, ``"afternoon"``, etc.) → returned as-is
          - ``"HH:MM"`` or ``"HH:MM:SS"`` string → parsed to hour
        """
        valid_bands = {"morning", "afternoon", "evening", "late_night"}

        if time_of_day is None:
            # Use the configured timezone (defaults to Montreal) so morning
            # routines trigger at the right local time even if the Pi runs UTC.
            try:
                from zoneinfo import ZoneInfo
                tz_name = self._cfg.get("timezone", "America/Toronto")
                local_hour = datetime.now(ZoneInfo(tz_name)).hour
            except (ImportError, KeyError):
                local_hour = datetime.now().hour
            return _hour_to_band(local_hour)

        if time_of_day in valid_bands:
            return time_of_day

        # Attempt to parse as a time string.
        match = re.match(r"^(\d{1,2}):", time_of_day)
        if match:
            hour = int(match.group(1))
            if 0 <= hour <= 23:
                return _hour_to_band(hour)

        log.warning(
            "Cannot resolve time_of_day %r to a band — defaulting to 'morning'.",
            time_of_day,
        )
        return "morning"

    def _validate_config(self) -> None:
        """Raise ValueError if required top-level sections are missing."""
        required = {"identity", "voice", "contexts", "residents", "accountability"}
        missing = required - self._cfg.keys()
        if missing:
            raise ValueError(
                f"personality.yaml is missing required sections: {missing}"
            )
