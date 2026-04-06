"""
AURA Content Radar — Creator Workflow Intelligence
===================================================
Tracks content creation sessions for each resident and acts as a proactive
producer: surfacing productivity patterns, nudging when the work is slipping,
and suggesting the optimal time to get back in the chair.

Content sessions are recorded whenever a content-related mode (streaming,
studio, podcast, music/DJ) is activated and then ended.  The ``log_session``
method is called by the voice agent's mode lifecycle hooks or by HA webhooks
decoded by the intent handler.

Design decisions
----------------
- Uses its own SQLite table (``content_sessions``) on the shared learning
  database path rather than a separate file, keeping all adaptive data
  co-located and simplifying backup.
- Claude generates nudge copy so the message tone matches AURA's personality
  and the resident's actual usage stats — not a canned string.
- ``suggest_content_time`` returns a structured dict so the dashboard can
  render it visually as well as the voice agent speaking it.
- All DB calls go through contextlib.closing so connections are never leaked.
- No hardcoded API keys or URLs — all credentials come from environment
  variables via the caller.

Usage (standalone, for testing)::

    HA_URL=http://homeassistant.local:8123 \\
    HA_TOKEN=... \\
    ANTHROPIC_API_KEY=... \\
    python content_radar.py
"""

from __future__ import annotations

import contextlib
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("aura.content_radar")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Valid content creation modes AURA can track.
CONTENT_MODES: frozenset[str] = frozenset(
    {"streaming", "studio", "podcast", "music"}
)

# Day names indexed by Python's weekday() (0 = Monday).
_DAY_NAMES = [
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday",
]

# SQL schema for the content sessions table.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS content_sessions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    person           TEXT    NOT NULL,
    mode             TEXT    NOT NULL,
    started_at       TEXT    NOT NULL,
    ended_at         TEXT    NOT NULL,
    duration_minutes REAL    NOT NULL,
    day_of_week      INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_content_sessions_person
    ON content_sessions (person, started_at);
"""


# ---------------------------------------------------------------------------
# ContentRadar
# ---------------------------------------------------------------------------


class ContentRadar:
    """
    Tracks content creation sessions and provides creator workflow intelligence.

    Parameters
    ----------
    ha_url:
        Base URL of the Home Assistant instance, e.g.
        ``http://homeassistant.local:8123``.  Stored for future HA queries
        (current mode state, media player status, etc.).
    ha_token:
        Long-lived access token for the HA REST API.
    db_path:
        Absolute path to the SQLite database file shared with the learning
        engine.  The ``content_sessions`` table is created here if absent.
    anthropic_api_key:
        API key for Claude nudge generation.  Loaded from the environment by
        the caller — never pass a literal string.
    """

    def __init__(
        self,
        ha_url: str,
        ha_token: str,
        db_path: str | Path,
        anthropic_api_key: str,
        claude_model: str = "claude-haiku-4-5-20251001",
    ) -> None:
        if not ha_token:
            log.warning("HA_TOKEN is not set — Home Assistant calls will fail.")
        if not anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY must not be empty.")

        self._ha_url: str = ha_url.rstrip("/")
        self._ha_headers: dict[str, str] = {
            "Authorization": f"Bearer {ha_token}",
            "Content-Type": "application/json",
        }
        self._db_path = Path(db_path)
        self._anthropic_api_key = anthropic_api_key
        self._claude_model = claude_model

        # Cache the Anthropic client instead of creating one per call
        import anthropic  # type: ignore[import-untyped]
        self._claude = anthropic.Anthropic(api_key=anthropic_api_key)

        self._ensure_db()
        log.info("ContentRadar initialised — db: %s  model: %s", self._db_path, claude_model)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log_session(
        self,
        person: str,
        mode: str,
        started_at: datetime,
        ended_at: datetime,
    ) -> None:
        """
        Record a completed content creation session.

        Parameters
        ----------
        person:
            Resident ID: ``"conaugh"`` or ``"adon"``.
        mode:
            Content creation mode.  Must be one of the values in
            ``CONTENT_MODES``: ``"streaming"``, ``"studio"``,
            ``"podcast"``, or ``"music"``.
        started_at:
            UTC datetime when the mode became active.
        ended_at:
            UTC datetime when the mode ended.  Must be after ``started_at``.

        Raises
        ------
        ValueError
            If ``mode`` is not a recognised content mode or if
            ``ended_at`` is not after ``started_at``.
        """
        mode = mode.lower().strip()
        if mode not in CONTENT_MODES:
            raise ValueError(
                f"Unknown content mode {mode!r}. "
                f"Valid modes: {sorted(CONTENT_MODES)}"
            )
        if ended_at <= started_at:
            raise ValueError("ended_at must be after started_at.")

        duration = (ended_at - started_at).total_seconds() / 60.0
        day_of_week = started_at.weekday()  # 0 = Monday

        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO content_sessions
                    (person, mode, started_at, ended_at, duration_minutes, day_of_week)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    person.lower(),
                    mode,
                    started_at.isoformat(),
                    ended_at.isoformat(),
                    round(duration, 2),
                    day_of_week,
                ),
            )

        log.info(
            "Session logged: %s / %s — %.1f min on %s",
            person,
            mode,
            duration,
            _DAY_NAMES[day_of_week],
        )

    def get_content_stats(self, person: str, days: int = 30) -> dict[str, Any]:
        """
        Return aggregated content creation statistics for ``person`` over the
        last ``days`` days.

        Returns
        -------
        dict with keys:
          - ``sessions_per_week``    (float)   — rolling 7-day average
          - ``most_productive_day``  (str)     — day name with most sessions
          - ``average_session_length`` (float) — average minutes per session
          - ``days_since_last_session`` (int)  — days since the last session
          - ``most_used_mode``       (str)     — most-activated content mode
          - ``total_sessions``       (int)     — total sessions in the window
          - ``total_minutes``        (float)   — total minutes in the window
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        person_key = person.lower()

        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT mode, started_at, ended_at, duration_minutes, day_of_week
                  FROM content_sessions
                 WHERE person = ? AND started_at >= ?
                 ORDER BY started_at ASC
                """,
                (person_key, cutoff),
            ).fetchall()

        if not rows:
            return {
                "sessions_per_week": 0.0,
                "most_productive_day": None,
                "average_session_length": 0.0,
                "days_since_last_session": days,
                "most_used_mode": None,
                "total_sessions": 0,
                "total_minutes": 0.0,
            }

        total_sessions = len(rows)
        total_minutes = sum(r["duration_minutes"] for r in rows)
        average_session_length = total_minutes / total_sessions

        # Sessions per week — based on the actual span of data
        sessions_per_week = (total_sessions / days) * 7

        # Most productive day
        day_counts: dict[int, int] = {}
        for r in rows:
            day_counts[r["day_of_week"]] = day_counts.get(r["day_of_week"], 0) + 1
        best_day_idx = max(day_counts, key=day_counts.__getitem__)
        most_productive_day = _DAY_NAMES[best_day_idx]

        # Most used mode
        mode_counts: dict[str, int] = {}
        for r in rows:
            mode_counts[r["mode"]] = mode_counts.get(r["mode"], 0) + 1
        most_used_mode = max(mode_counts, key=mode_counts.__getitem__)

        # Days since last session
        last_started = rows[-1]["started_at"]
        last_dt = datetime.fromisoformat(last_started)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        now_utc = datetime.now(timezone.utc)
        days_since = max(0, (now_utc - last_dt).days)

        return {
            "sessions_per_week": round(sessions_per_week, 1),
            "most_productive_day": most_productive_day,
            "average_session_length": round(average_session_length, 1),
            "days_since_last_session": days_since,
            "most_used_mode": most_used_mode,
            "total_sessions": total_sessions,
            "total_minutes": round(total_minutes, 1),
        }

    def generate_nudge(self, person: str) -> Optional[str]:
        """
        Generate a contextual creator nudge for ``person`` via Claude if they
        have been inactive for more than 5 days.

        Returns ``None`` if the resident has created content recently (within
        5 days) — no nudge needed.

        Returns
        -------
        str | None
            Conversational nudge text ready for TTS, or ``None`` if the
            resident is recently active.
        """
        stats = self.get_content_stats(person, days=30)
        days_since = stats["days_since_last_session"]

        if days_since <= 5:
            log.debug(
                "%s last created content %d day(s) ago — no nudge needed.",
                person,
                days_since,
            )
            return None

        # Build rich context for Claude to generate a personalised nudge
        most_productive_day = stats["most_productive_day"] or "the weekend"
        avg_length = stats["average_session_length"]
        mode = stats["most_used_mode"] or "studio"
        sessions_pw = stats["sessions_per_week"]

        display_name = person.capitalize()

        prompt = (
            f"You are AURA, the smart home AI for {display_name}. "
            f"You are their creative accountability partner — witty, direct, "
            f"warm, not preachy. "
            f"\n\nContent stats for {display_name}:"
            f"\n- Days since last content session: {days_since}"
            f"\n- Most productive day historically: {most_productive_day} evenings"
            f"\n- Average session length: {avg_length:.0f} minutes"
            f"\n- Most-used mode: {mode}"
            f"\n- Normal cadence: {sessions_pw:.1f} sessions per week"
            f"\n\nGenerate a single short spoken nudge (2-3 sentences max) "
            f"reminding {display_name} to create content. "
            f"Reference the actual stats naturally. "
            f"End with an offer to set up {mode} mode. "
            f"Keep it real — not corporate, not cheesy. "
            f"Do NOT use markdown. Return only the spoken text."
        )

        try:
            message = self._claude.messages.create(
                model=self._claude_model,
                max_tokens=150,
                temperature=0.7,
                messages=[{"role": "user", "content": prompt}],
            )
            nudge_text: str = message.content[0].text.strip()
            log.info("Content nudge generated for %s: %r", person, nudge_text[:80])
            return nudge_text

        except Exception as exc:  # noqa: BLE001
            log.error("Failed to generate content nudge via Claude: %s", exc)
            # Fallback to a template nudge so the voice agent still has something
            return (
                f"Yo {display_name}, it's been {days_since} days since your last "
                f"{mode} session. Your best work usually happens on "
                f"{most_productive_day}s. Want me to set up {mode} mode?"
            )

    def suggest_content_time(self, person: str) -> dict[str, Any]:
        """
        Analyse historical content sessions to recommend the best upcoming
        time slot for a creation session.

        Looks at the last 60 days of sessions to find the hour and day of week
        that correlate with the longest, most consistent sessions.

        Returns
        -------
        dict with keys:
          - ``best_day``        (str)   — recommended day name
          - ``best_hour``       (int)   — recommended start hour (24-hour)
          - ``best_hour_label`` (str)   — human-readable label, e.g. "7 PM"
          - ``avg_duration``    (float) — expected session length in minutes
          - ``confidence``      (float) — 0.0–1.0 based on sample count
          - ``reasoning``       (str)   — plain text explanation for TTS
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        person_key = person.lower()

        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT day_of_week, duration_minutes,
                       CAST(strftime('%H', started_at) AS INTEGER) AS start_hour
                  FROM content_sessions
                 WHERE person = ? AND started_at >= ?
                """,
                (person_key, cutoff),
            ).fetchall()

        if not rows:
            return {
                "best_day": "Tuesday",
                "best_hour": 19,
                "best_hour_label": "7 PM",
                "avg_duration": 0.0,
                "confidence": 0.0,
                "reasoning": (
                    "Not enough history yet to make a recommendation. "
                    "Try creating some content first and I'll learn your patterns."
                ),
            }

        # Group by (day_of_week, hour) and compute average duration + count
        slot_data: dict[tuple[int, int], list[float]] = {}
        for r in rows:
            key = (r["day_of_week"], r["start_hour"])
            slot_data.setdefault(key, []).append(r["duration_minutes"])

        # Score each slot: average duration * sqrt(sample_count) to reward
        # both productivity and consistency
        import math

        best_slot: tuple[int, int] | None = None
        best_score = -1.0
        for (dow, hour), durations in slot_data.items():
            n = len(durations)
            avg = sum(durations) / n
            score = avg * math.sqrt(n)
            if score > best_score:
                best_score = score
                best_slot = (dow, hour)

        if best_slot is None:
            # Should not happen but satisfy the type checker
            best_slot = (1, 19)  # Tuesday 7 PM

        best_day_idx, best_hour = best_slot
        best_day = _DAY_NAMES[best_day_idx]
        best_hour_label = _fmt_hour(best_hour)

        best_durations = slot_data[best_slot]
        avg_duration = sum(best_durations) / len(best_durations)
        sample_count = len(best_durations)
        confidence = min(1.0, sample_count / 5.0)  # full confidence at 5+ samples

        reasoning = (
            f"Your best content sessions tend to start on {best_day}s "
            f"around {best_hour_label}. "
            f"Average session runs about {avg_duration:.0f} minutes — "
            f"that's when you're most locked in."
        )

        return {
            "best_day": best_day,
            "best_hour": best_hour,
            "best_hour_label": best_hour_label,
            "avg_duration": round(avg_duration, 1),
            "confidence": round(confidence, 2),
            "reasoning": reasoning,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ensure_db(self) -> None:
        """Create the ``content_sessions`` table if it does not yet exist."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as conn:
            conn.executescript(_SCHEMA)
        log.debug("content_sessions schema ensured at %s", self._db_path)

    @contextlib.contextmanager
    def _connection(self):  # type: ignore[return]
        """Yield a sqlite3 connection with row_factory set, auto-committing."""
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Internal utilities
# ---------------------------------------------------------------------------


def _fmt_hour(hour: int) -> str:
    """Format a 24-hour integer as a human-readable label, e.g. 19 → '7 PM'."""
    if hour == 0:
        return "12 AM"
    if hour < 12:
        return f"{hour} AM"
    if hour == 12:
        return "12 PM"
    return f"{hour - 12} PM"


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _cli() -> None:
    """
    Standalone test runner.

    Usage::

        HA_URL=http://homeassistant.local:8123 \\
        HA_TOKEN=... \\
        ANTHROPIC_API_KEY=... \\
        python content_radar.py
    """
    import os

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )

    ha_url = os.environ.get("HA_URL", "http://homeassistant.local:8123")
    ha_token = os.environ.get("HA_TOKEN", "")
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    db_path = os.environ.get("AURA_DB_PATH", "/tmp/aura_test.db")

    radar = ContentRadar(
        ha_url=ha_url,
        ha_token=ha_token,
        db_path=db_path,
        anthropic_api_key=api_key,
    )

    # Log a sample session
    now = datetime.now(timezone.utc)
    radar.log_session(
        person="conaugh",
        mode="studio",
        started_at=now - timedelta(hours=2),
        ended_at=now - timedelta(hours=1),
    )

    stats = radar.get_content_stats("conaugh")
    log.info("Stats: %s", stats)

    suggestion = radar.suggest_content_time("conaugh")
    log.info("Suggestion: %s", suggestion)


if __name__ == "__main__":
    _cli()
