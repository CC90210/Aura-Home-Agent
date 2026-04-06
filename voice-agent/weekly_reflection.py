"""
AURA Weekly Reflection — Sunday Evening Life Review
====================================================
Every Sunday evening, AURA initiates a natural conversation summarizing
the week: best day, worst day, habit streaks, patterns noticed, and
a forward-looking question about the week ahead.

Unlike the daily pulse check (which is quick and habit-focused), the
weekly reflection is deeper — it looks at trends, celebrates consistency,
and gently surfaces areas that slipped.

Designed to feel like a friend sitting down with you on Sunday night
and saying "so, how was your week, really?"

Usage (standalone):
    python weekly_reflection.py conaugh
    python weekly_reflection.py adon
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("aura.weekly_reflection")

_STATE_FILE = Path("/config/aura/data/weekly_reflections.json")
if not _STATE_FILE.parent.exists():
    _STATE_FILE = Path(__file__).parent.parent / "memory" / "weekly_reflections.json"

# Claude settings (match intent_handler for consistency)
_CLAUDE_MODEL = "claude-sonnet-4-6"
_CLAUDE_MAX_TOKENS = 500
_CLAUDE_TEMPERATURE = 0.8


class WeeklyReflection:
    """Generates and manages weekly reflection conversations."""

    def __init__(self, habit_tracker=None, personality=None):
        self._habit_tracker = habit_tracker
        self._personality = personality
        self._history = self._load_history()

        # Claude client
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            env_path = Path(__file__).parent.parent / ".env"
            if env_path.exists():
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    if line.startswith("ANTHROPIC_API_KEY="):
                        api_key = line.split("=", 1)[1].strip().strip('"')
        try:
            import anthropic
            self._claude = anthropic.Anthropic(api_key=api_key) if api_key else None
        except ImportError:
            self._claude = None

    def _load_history(self) -> dict:
        try:
            if _STATE_FILE.exists():
                return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _save_history(self):
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(
            json.dumps(self._history, indent=2, default=str),
            encoding="utf-8"
        )

    def should_reflect(self, person: str) -> bool:
        """Returns True if it's Sunday evening and we haven't reflected this week."""
        now = datetime.now()
        if now.weekday() != 6:  # 6 = Sunday
            return False
        if now.hour < 18 or now.hour > 23:  # 6pm - 11pm window
            return False

        # Check if already reflected this week
        last = self._history.get(person, {}).get("last_reflection")
        if last:
            try:
                last_dt = datetime.fromisoformat(last)
                if (now - last_dt).days < 5:  # Don't repeat within 5 days
                    return False
            except Exception:
                pass
        return True

    def generate_reflection(self, person: str) -> str:
        """Generate the weekly reflection message using Claude + habit data."""
        if not self._claude:
            return self._fallback_reflection(person)

        log.info("Generating weekly reflection for %s", person)

        # Gather week data
        week_data = self._gather_week_data(person)
        system_prompt = self._build_reflection_prompt(person, week_data)

        user_msg = (
            f"Generate a Sunday evening weekly reflection for {person}. "
            f"Use the week data in the system prompt. "
            f"Summarize the week honestly — celebrate wins, acknowledge misses. "
            f"Identify the best day and worst day. "
            f"Spot one pattern they might not have noticed. "
            f"End with a question about what they want next week to look like. "
            f"Keep it under 6 sentences. Sound like a friend, not a coach."
        )

        try:
            response = self._claude.messages.create(
                model=_CLAUDE_MODEL,
                max_tokens=_CLAUDE_MAX_TOKENS,
                temperature=_CLAUDE_TEMPERATURE,
                system=system_prompt,
                messages=[{"role": "user", "content": user_msg}],
            )
            text = response.content[0].text.strip()
        except Exception as e:
            log.error("Claude API error for weekly reflection: %s", e)
            return self._fallback_reflection(person)

        # Record
        self._history.setdefault(person, {})
        self._history[person]["last_reflection"] = datetime.now(timezone.utc).isoformat()
        self._history[person]["last_text"] = text[:500]
        self._save_history()

        return text

    def _gather_week_data(self, person: str) -> dict[str, Any]:
        """Pull the last 7 days of habit data."""
        if not self._habit_tracker:
            return {"note": "No habit data available"}

        try:
            weekly = self._habit_tracker.get_weekly_report(person)
            return {
                "streaks": weekly.streaks,
                "completion_trend": weekly.completion_trend,
                "best_habit": weekly.best_habit,
                "worst_habit": weekly.worst_habit,
                "daily_summaries": [
                    {
                        "date": str(d.report_date),
                        "completion_rate": d.completion_rate,
                        "completed": [e.habit_type for e in d.entries if e.completed],
                        "missed": [e.habit_type for e in d.entries if not e.completed],
                    }
                    for d in weekly.daily_reports
                ],
            }
        except Exception as e:
            log.error("Failed to gather week data: %s", e)
            return {"error": str(e)}

    def _build_reflection_prompt(self, person: str, week_data: dict) -> str:
        """Build the system prompt for the reflection."""
        # Get personality base
        personality_block = ""
        if self._personality:
            personality_block = self._personality.get_system_prompt(
                person=person, context="accountability_check", time_of_day="evening"
            )

        return f"""{personality_block}

You are doing a WEEKLY REFLECTION — this is different from a daily pulse check.
This is Sunday evening. The week is wrapping up. Be reflective, not commanding.

TONE: Like a friend sitting on the couch with them, beer in hand, saying
"so how was the week, really?" Celebrate consistency. Be honest about gaps.
Spot patterns they might not see. Always end hopeful.

WEEK DATA:
{json.dumps(week_data, indent=2, default=str)}

RULES:
- Mention specific days if the data shows them ("Tuesday and Thursday were strong")
- If a habit was perfect all week, celebrate it hard
- If a habit was missed 3+ times, address it directly but not harshly
- Spot correlations ("you tend to skip gym on days you stay up late")
- End with: what do you want next week to look like?
- Under 6 sentences. No lists. Natural speech."""

    def _fallback_reflection(self, person: str) -> str:
        """Fallback when Claude is unavailable."""
        name = person.capitalize()
        return (
            f"Hey {name}, it's Sunday. Week's wrapping up. "
            f"Take a sec to think about what went well and what you'd change. "
            f"What's the one thing you want to lock in this coming week?"
        )

    def record_response(self, person: str, response: str):
        """Record the resident's verbal response to the reflection."""
        self._history.setdefault(person, {})
        self._history[person]["last_response"] = response[:500]
        self._history[person]["response_at"] = datetime.now(timezone.utc).isoformat()
        self._save_history()
        log.info("Recorded %s's reflection response", person)


# Standalone test
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    person = sys.argv[1] if len(sys.argv) > 1 else "conaugh"
    wr = WeeklyReflection()
    print(wr.generate_reflection(person))
