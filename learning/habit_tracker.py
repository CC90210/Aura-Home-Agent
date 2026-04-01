"""
AURA Adaptive Learning — Habit Tracker
========================================
Tracks daily habits for both residents (Conaugh and Adon) and provides
accountability nudges when habits slip.

Habits are detected two ways:

  Automatic  — inferred from HA entity states stored in the pattern_engine
               events table (e.g. person left home during the gym window,
               studio mode ran for >= 60 min, goodnight scene fired on time).

  Manual     — explicitly logged via ``log_habit()``, typically driven by the
               voice agent ("Hey Aura, mark gym done for today").

Reports
-------
``get_daily_report``  — what each habit looked like on a specific date.
``get_weekly_report`` — 7-day summary with per-habit streaks and trends.
``get_accountability_nudge`` — contextual reminder text if habits are slipping,
                               styled in AURA's "homie" tone.

The tracker reads from the same SQLite database as PatternEngine so it has
access to the full event history without duplicating storage.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Optional

import yaml

# Reuse DB and config infrastructure from pattern_engine
from .pattern_engine import _Database, _load_config

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log = logging.getLogger("aura.habit_tracker")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HABIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS habit_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    person      TEXT    NOT NULL,
    habit_type  TEXT    NOT NULL,
    completed   INTEGER NOT NULL DEFAULT 0,
    log_date    TEXT    NOT NULL,
    logged_at   TEXT    NOT NULL,
    source      TEXT    NOT NULL DEFAULT 'manual'
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_habit_logs_person_date
    ON habit_logs (person, habit_type, log_date);
"""

# Nudge templates keyed by habit_type.  {person} and {streak} are formatted in.
_NUDGE_TEMPLATES: dict[str, str] = {
    "wake_up_on_time": (
        "Yo {person}, you've missed your wake target {streak} day(s) in a row. "
        "Early morning sets the tone for everything — let's get back on it."
    ),
    "gym": (
        "Hey {person}, you've skipped the gym {streak} day(s) straight. "
        "Even 20 mins counts — don't let the streak die."
    ),
    "deep_work": (
        "{person}, you haven't had a solid deep work session in {streak} day(s). "
        "Block off a studio slot today — the work doesn't do itself."
    ),
    "healthy_dinner": (
        "Checking in {person} — {streak} day(s) without logging dinner. "
        "Fuel matters. You know this."
    ),
    "bedtime": (
        "{person}, you've been going to bed late {streak} day(s) running. "
        "Sleep is the cheat code — get it locked in."
    ),
    "_default": (
        "Hey {person}, you've missed '{habit}' {streak} day(s) in a row. "
        "AURA's got you — don't let it slip further."
    ),
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class HabitEntry:
    """A single day's record for one habit and one person."""

    person: str
    habit_type: str
    completed: bool
    log_date: date
    logged_at: datetime
    source: str  # 'manual' | 'auto'


@dataclass
class DailyReport:
    """All habit outcomes for one person on one day."""

    person: str
    report_date: date
    entries: list[HabitEntry]
    completion_rate: float  # 0.0–1.0

    @property
    def summary(self) -> str:
        done = sum(1 for e in self.entries if e.completed)
        total = len(self.entries)
        return f"{done}/{total} habits completed on {self.report_date}"


@dataclass
class WeeklyReport:
    """Seven-day summary for one person."""

    person: str
    week_ending: date
    daily_reports: list[DailyReport]
    streaks: dict[str, int]   # habit_type → current streak
    completion_trend: list[float]  # daily completion rates, oldest first
    best_habit: Optional[str]
    worst_habit: Optional[str]

    @property
    def average_completion(self) -> float:
        if not self.completion_trend:
            return 0.0
        return sum(self.completion_trend) / len(self.completion_trend)


@dataclass
class AccountabilityNudge:
    """A contextual reminder message for a specific person and habit."""

    person: str
    habit_type: str
    missed_streak: int
    message: str
    generated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ---------------------------------------------------------------------------
# HabitTracker
# ---------------------------------------------------------------------------


class HabitTracker:
    """
    Tracks daily habits for Conaugh and Adon and provides accountability nudges.

    Habits can be logged manually (via ``log_habit``) or detected automatically
    from the events table that PatternEngine populates.  Auto-detection runs
    when ``auto_detect_habits`` is called — typically once per day via a cron
    job or HA time-based automation.

    Parameters
    ----------
    config_path:
        Optional override for the YAML config file path.
    """

    def __init__(self, config_path: Optional[Path] = None) -> None:
        if config_path is not None:
            with config_path.open("r", encoding="utf-8") as fh:
                self._config = yaml.safe_load(fh)
        else:
            self._config = _load_config()

        self._db = _Database(self._config["database"]["path"])
        self._extend_schema()

        habits_cfg = self._config.get("habits", {})
        self._tracked_habits: list[dict] = habits_cfg.get("tracked_habits", [])
        self._nudge_threshold: int = int(
            habits_cfg.get("accountability", {}).get("nudge_threshold", 2)
        )
        self._persons: list[dict] = self._config.get("persons", [])

        log.info(
            "HabitTracker initialised — tracking %d habit(s) for %d person(s)",
            len(self._tracked_habits),
            len(self._persons),
        )

    # ------------------------------------------------------------------
    # Public API — logging
    # ------------------------------------------------------------------

    def log_habit(
        self,
        person: str,
        habit_type: str,
        completed: bool,
        timestamp: Optional[datetime] = None,
        source: str = "manual",
    ) -> None:
        """
        Record whether ``person`` completed ``habit_type`` on the date
        implied by ``timestamp`` (defaults to now).

        Calling this twice for the same person / habit / date updates the
        existing record (UPSERT) so idempotent re-logging is safe.

        Parameters
        ----------
        person:
            Resident ID: 'conaugh' or 'adon'.
        habit_type:
            Must match a name in the ``tracked_habits`` config list.
        completed:
            True if the habit was completed.
        timestamp:
            Timestamp for the log entry.  Defaults to now (UTC).
        source:
            'manual' for explicit logs, 'auto' for system-detected.
        """
        if not self._is_known_person(person):
            log.warning("Unknown person '%s' — habit not logged.", person)
            return

        ts = timestamp or datetime.now(timezone.utc)
        log_date = ts.date().isoformat()
        logged_at = ts.isoformat()

        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO habit_logs (person, habit_type, completed, log_date,
                                        logged_at, source)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (person, habit_type, log_date)
                DO UPDATE SET completed  = excluded.completed,
                              logged_at  = excluded.logged_at,
                              source     = excluded.source
                """,
                (person, habit_type, int(completed), log_date, logged_at, source),
            )

        status = "completed" if completed else "missed"
        log.info(
            "Habit logged: %s / %s → %s (source=%s, date=%s)",
            person,
            habit_type,
            status,
            source,
            log_date,
        )

    # ------------------------------------------------------------------
    # Public API — auto-detection
    # ------------------------------------------------------------------

    def auto_detect_habits(
        self, target_date: Optional[date] = None
    ) -> dict[str, list[str]]:
        """
        Scan the events table to auto-detect completed habits for
        ``target_date`` (defaults to yesterday, since today may still be in
        progress for most habits).

        Returns a dict mapping person ID to list of auto-detected habit names.
        """
        check_date = target_date or (date.today() - timedelta(days=1))
        detected: dict[str, list[str]] = {p["id"]: [] for p in self._persons}

        for habit_cfg in self._tracked_habits:
            habit_name: str = habit_cfg["name"]
            detection_method: str = habit_cfg.get("detection", "manual_log")

            if detection_method == "manual_log":
                continue  # Cannot auto-detect; requires explicit log call

            for person in self._persons:
                pid = person["id"]
                phone_entity = person.get("phone_entity", "")

                completed = False

                if detection_method == "first_light_on_or_motion":
                    completed = self._detect_wake(habit_cfg, check_date)

                elif detection_method == "left_home_during_window":
                    completed = self._detect_gym(
                        habit_cfg, check_date, phone_entity
                    )

                elif detection_method == "studio_mode_duration":
                    completed = self._detect_deep_work(habit_cfg, check_date)

                elif detection_method == "goodnight_scene_activated":
                    completed = self._detect_bedtime(habit_cfg, check_date)

                if completed:
                    self.log_habit(
                        person=pid,
                        habit_type=habit_name,
                        completed=True,
                        timestamp=datetime.combine(
                            check_date, time(23, 59), tzinfo=timezone.utc
                        ),
                        source="auto",
                    )
                    detected[pid].append(habit_name)
                else:
                    # Explicitly record a miss so streaks are accurate
                    # Only write if there's no existing manual entry for the day
                    existing = self._db.execute(
                        """
                        SELECT completed FROM habit_logs
                         WHERE person = ? AND habit_type = ? AND log_date = ?
                        """,
                        (pid, habit_name, check_date.isoformat()),
                    )
                    if not existing:
                        self.log_habit(
                            person=pid,
                            habit_type=habit_name,
                            completed=False,
                            timestamp=datetime.combine(
                                check_date, time(23, 59), tzinfo=timezone.utc
                            ),
                            source="auto",
                        )

        log.info(
            "Auto-detection complete for %s — results: %s",
            check_date,
            {k: v for k, v in detected.items() if v},
        )
        return detected

    # ------------------------------------------------------------------
    # Public API — queries
    # ------------------------------------------------------------------

    def get_streak(self, person: str, habit_type: str) -> int:
        """
        Return the number of consecutive days (counting backwards from
        yesterday) on which ``person`` completed ``habit_type``.

        A streak of 0 means the habit was missed or not logged yesterday.

        Parameters
        ----------
        person:
            Resident ID.
        habit_type:
            Habit name as defined in config.

        Returns
        -------
        int
            Current consecutive-day streak.
        """
        streak = 0
        check = date.today() - timedelta(days=1)

        for _ in range(365):  # cap at one year to avoid infinite loops
            rows = self._db.execute(
                """
                SELECT completed FROM habit_logs
                 WHERE person = ? AND habit_type = ? AND log_date = ?
                """,
                (person, habit_type, check.isoformat()),
            )
            if rows and rows[0]["completed"] == 1:
                streak += 1
                check -= timedelta(days=1)
            else:
                break

        return streak

    def get_daily_report(
        self, person: str, report_date: Optional[date] = None
    ) -> DailyReport:
        """
        Return a ``DailyReport`` for ``person`` on ``report_date``
        (defaults to today).

        Parameters
        ----------
        person:
            Resident ID.
        report_date:
            The date to report on.  Defaults to today.

        Returns
        -------
        DailyReport
            Contains one ``HabitEntry`` per tracked habit.  Habits with no
            log entry for that day are included as not-completed.
        """
        target = report_date or date.today()
        rows = self._db.execute(
            """
            SELECT habit_type, completed, log_date, logged_at, source
              FROM habit_logs
             WHERE person = ? AND log_date = ?
            """,
            (person, target.isoformat()),
        )

        logged: dict[str, HabitEntry] = {}
        for row in rows:
            logged[row["habit_type"]] = HabitEntry(
                person=person,
                habit_type=row["habit_type"],
                completed=bool(row["completed"]),
                log_date=date.fromisoformat(row["log_date"]),
                logged_at=datetime.fromisoformat(row["logged_at"]),
                source=row["source"],
            )

        # Fill in unlogged habits as not completed
        entries: list[HabitEntry] = []
        for habit_cfg in self._tracked_habits:
            name = habit_cfg["name"]
            if name in logged:
                entries.append(logged[name])
            else:
                entries.append(
                    HabitEntry(
                        person=person,
                        habit_type=name,
                        completed=False,
                        log_date=target,
                        logged_at=datetime.combine(
                            target, time(0, 0), tzinfo=timezone.utc
                        ),
                        source="not_logged",
                    )
                )

        total = len(entries)
        completion_rate = (
            sum(1 for e in entries if e.completed) / total if total > 0 else 0.0
        )

        return DailyReport(
            person=person,
            report_date=target,
            entries=entries,
            completion_rate=completion_rate,
        )

    def get_weekly_report(self, person: str) -> WeeklyReport:
        """
        Return a ``WeeklyReport`` for the last 7 days (today inclusive).

        Parameters
        ----------
        person:
            Resident ID.

        Returns
        -------
        WeeklyReport
            Includes daily reports, per-habit streaks, completion trend, and
            best/worst habit identification.
        """
        today = date.today()
        daily_reports: list[DailyReport] = []

        for offset in range(6, -1, -1):  # 6 days ago → today
            day = today - timedelta(days=offset)
            daily_reports.append(self.get_daily_report(person, day))

        completion_trend = [r.completion_rate for r in daily_reports]

        # Streaks per habit
        streaks = {
            habit_cfg["name"]: self.get_streak(person, habit_cfg["name"])
            for habit_cfg in self._tracked_habits
        }

        # Best / worst habits over the week
        habit_rates: dict[str, list[float]] = {h["name"]: [] for h in self._tracked_habits}
        for daily in daily_reports:
            for entry in daily.entries:
                habit_rates[entry.habit_type].append(1.0 if entry.completed else 0.0)

        avg_rates = {
            h: (sum(vals) / len(vals) if vals else 0.0)
            for h, vals in habit_rates.items()
        }

        best = max(avg_rates, key=avg_rates.get) if avg_rates else None  # type: ignore[arg-type]
        worst = min(avg_rates, key=avg_rates.get) if avg_rates else None  # type: ignore[arg-type]

        # Don't label a habit as "worst" if it was never logged
        if worst and avg_rates.get(worst, 0.0) == 0.0 and all(
            v == 0.0 for v in avg_rates.values()
        ):
            worst = None

        return WeeklyReport(
            person=person,
            week_ending=today,
            daily_reports=daily_reports,
            streaks=streaks,
            completion_trend=completion_trend,
            best_habit=best,
            worst_habit=worst,
        )

    def get_accountability_nudge(self, person: str) -> Optional[AccountabilityNudge]:
        """
        Return an ``AccountabilityNudge`` if any habit has been missed for
        ``nudge_threshold`` or more consecutive days.

        The "worst" offending habit (longest miss streak) is selected.
        Returns None if the resident is on track across all habits.

        Parameters
        ----------
        person:
            Resident ID.
        """
        if not self._is_known_person(person):
            log.warning("Unknown person '%s' — cannot generate nudge.", person)
            return None

        person_cfg = next(
            (p for p in self._persons if p["id"] == person), {}
        )
        display_name = person_cfg.get("display_name", person.capitalize())

        worst_habit: Optional[str] = None
        worst_miss_streak = 0

        for habit_cfg in self._tracked_habits:
            habit_name = habit_cfg["name"]
            miss_streak = self._miss_streak(person, habit_name)
            if miss_streak >= self._nudge_threshold and miss_streak > worst_miss_streak:
                worst_miss_streak = miss_streak
                worst_habit = habit_name

        if worst_habit is None:
            return None  # All good

        template = _NUDGE_TEMPLATES.get(worst_habit, _NUDGE_TEMPLATES["_default"])
        message = template.format(
            person=display_name,
            streak=worst_miss_streak,
            habit=worst_habit.replace("_", " "),
        )

        return AccountabilityNudge(
            person=person,
            habit_type=worst_habit,
            missed_streak=worst_miss_streak,
            message=message,
        )

    def format_weekly_summary(self, person: str) -> str:
        """
        Format the weekly report as a natural-language string suitable for
        the voice agent to read aloud.

        Example
        -------
        "Here's the weekly rundown for Conaugh. You completed 4 out of 5
         habits on average this week. Your strongest habit was deep_work —
         you nailed it 6 out of 7 days. Bedtime needs some work — only 2
         out of 7 days on target. Current streaks: gym 3 days, wake_up_on_time
         5 days."
        """
        report = self.get_weekly_report(person)
        person_cfg = next((p for p in self._persons if p["id"] == person), {})
        display_name = person_cfg.get("display_name", person.capitalize())

        avg_pct = report.average_completion * 100
        total_habits = len(self._tracked_habits)

        lines: list[str] = [
            f"Here's the weekly rundown for {display_name}.",
            f"You averaged {avg_pct:.0f}% completion across {total_habits} habits.",
        ]

        if report.best_habit:
            best_display = report.best_habit.replace("_", " ")
            lines.append(f"Strongest habit this week: {best_display}.")

        if report.worst_habit and report.worst_habit != report.best_habit:
            worst_display = report.worst_habit.replace("_", " ")
            lines.append(f"Needs work: {worst_display}.")

        streak_parts = [
            f"{h.replace('_', ' ')} ({v} day{'s' if v != 1 else ''})"
            for h, v in report.streaks.items()
            if v > 0
        ]
        if streak_parts:
            lines.append("Active streaks: " + ", ".join(streak_parts) + ".")

        nudge = self.get_accountability_nudge(person)
        if nudge:
            lines.append(nudge.message)

        return "  ".join(lines)

    # ------------------------------------------------------------------
    # Auto-detection helpers — private
    # ------------------------------------------------------------------

    def _detect_wake(self, habit_cfg: dict, check_date: date) -> bool:
        """
        Detect whether the residents woke up on time by checking whether any
        light entity or motion sensor fired before the target time + tolerance.
        """
        target_str: str = habit_cfg.get("target_time", "06:30")
        tolerance: int = int(habit_cfg.get("tolerance_minutes", 15))

        target_h, target_m = map(int, target_str.split(":"))
        deadline = datetime.combine(
            check_date,
            time(target_h, target_m),
            tzinfo=timezone.utc,
        ) + timedelta(minutes=tolerance)

        day_start = datetime.combine(
            check_date, time(4, 0), tzinfo=timezone.utc
        ).isoformat()
        deadline_str = deadline.isoformat()

        rows = self._db.execute(
            """
            SELECT 1 FROM events
             WHERE (entity_id LIKE 'light.%' OR entity_id LIKE 'binary_sensor.%')
               AND new_state IN ('on', 'detected')
               AND timestamp BETWEEN ? AND ?
             LIMIT 1
            """,
            (day_start, deadline_str),
        )
        return len(rows) > 0

    def _detect_gym(
        self, habit_cfg: dict, check_date: date, phone_entity: str
    ) -> bool:
        """
        Detect gym attendance by checking whether the resident's phone entity
        transitioned to 'not_home' during the configured gym window.
        """
        window_str: str = habit_cfg.get("window", "06:30-08:30")
        start_str, end_str = window_str.split("-")
        sh, sm = map(int, start_str.split(":"))
        eh, em = map(int, end_str.split(":"))

        window_start = datetime.combine(
            check_date, time(sh, sm), tzinfo=timezone.utc
        ).isoformat()
        window_end = datetime.combine(
            check_date, time(eh, em), tzinfo=timezone.utc
        ).isoformat()

        if not phone_entity:
            return False

        rows = self._db.execute(
            """
            SELECT 1 FROM events
             WHERE entity_id = ?
               AND new_state = 'not_home'
               AND timestamp BETWEEN ? AND ?
             LIMIT 1
            """,
            (phone_entity, window_start, window_end),
        )
        return len(rows) > 0

    def _detect_deep_work(self, habit_cfg: dict, check_date: date) -> bool:
        """
        Detect a deep work session by checking whether studio_mode_active was
        switched on for at least ``min_duration_minutes`` during the day.
        """
        min_dur: int = int(habit_cfg.get("min_duration_minutes", 60))

        day_start = datetime.combine(
            check_date, time(0, 0), tzinfo=timezone.utc
        ).isoformat()
        day_end = datetime.combine(
            check_date, time(23, 59, 59), tzinfo=timezone.utc
        ).isoformat()

        # Find all on/off transitions for the studio boolean on this day
        rows = self._db.execute(
            """
            SELECT new_state, timestamp FROM events
             WHERE entity_id = 'input_boolean.studio_mode_active'
               AND new_state IN ('on', 'off')
               AND timestamp BETWEEN ? AND ?
             ORDER BY timestamp ASC
            """,
            (day_start, day_end),
        )

        total_minutes = 0.0
        on_ts: Optional[datetime] = None

        for row in rows:
            if row["new_state"] == "on":
                on_ts = datetime.fromisoformat(row["timestamp"])
            elif row["new_state"] == "off" and on_ts is not None:
                off_ts = datetime.fromisoformat(row["timestamp"])
                total_minutes += (off_ts - on_ts).total_seconds() / 60.0
                on_ts = None

        return total_minutes >= min_dur

    def _detect_bedtime(self, habit_cfg: dict, check_date: date) -> bool:
        """
        Detect whether the goodnight scene was activated within the target
        bedtime window.
        """
        target_str: str = habit_cfg.get("target_time", "23:00")
        tolerance: int = int(habit_cfg.get("tolerance_minutes", 30))

        th, tm = map(int, target_str.split(":"))
        target_dt = datetime.combine(
            check_date, time(th, tm), tzinfo=timezone.utc
        )
        window_start = (target_dt - timedelta(minutes=tolerance)).isoformat()
        # Bedtime can spill past midnight — allow up to tolerance after target
        window_end = (target_dt + timedelta(minutes=tolerance)).isoformat()

        rows = self._db.execute(
            """
            SELECT 1 FROM events
             WHERE event_type IN ('scene_activated', 'automation_fired')
               AND (entity_id LIKE '%goodnight%' OR triggered_by LIKE '%goodnight%')
               AND timestamp BETWEEN ? AND ?
             LIMIT 1
            """,
            (window_start, window_end),
        )
        return len(rows) > 0

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    def _miss_streak(self, person: str, habit_type: str) -> int:
        """
        Return the number of consecutive days (backwards from yesterday) on
        which ``habit_type`` was NOT completed by ``person``.
        """
        streak = 0
        check = date.today() - timedelta(days=1)

        for _ in range(365):
            rows = self._db.execute(
                """
                SELECT completed FROM habit_logs
                 WHERE person = ? AND habit_type = ? AND log_date = ?
                """,
                (person, habit_type, check.isoformat()),
            )
            if rows and rows[0]["completed"] == 0:
                streak += 1
                check -= timedelta(days=1)
            elif not rows:
                # No entry means no information — treat as missed for nudge purposes
                streak += 1
                check -= timedelta(days=1)
            else:
                break

        return streak

    def _is_known_person(self, person: str) -> bool:
        return any(p["id"] == person for p in self._persons)

    def _extend_schema(self) -> None:
        """Add habit-specific tables to the shared database."""
        with self._db.transaction() as conn:
            conn.executescript(_HABIT_SCHEMA)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _cli() -> None:
    """
    Usage
    -----
    python habit_tracker.py report conaugh
    python habit_tracker.py weekly conaugh
    python habit_tracker.py nudge adon
    python habit_tracker.py autodetect
    """
    import argparse

    parser = argparse.ArgumentParser(description="AURA Habit Tracker — standalone CLI")
    sub = parser.add_subparsers(dest="command")

    rep = sub.add_parser("report", help="Daily report for a person")
    rep.add_argument("person")

    weekly = sub.add_parser("weekly", help="Weekly summary for a person")
    weekly.add_argument("person")

    nudge = sub.add_parser("nudge", help="Accountability nudge for a person")
    nudge.add_argument("person")

    sub.add_parser("autodetect", help="Auto-detect habits for yesterday")

    args = parser.parse_args()
    tracker = HabitTracker()

    if args.command == "report":
        report = tracker.get_daily_report(args.person)
        log.info(report.summary)
        for entry in report.entries:
            status = "done" if entry.completed else "missed"
            log.info("  %s — %s", entry.habit_type, status)

    elif args.command == "weekly":
        summary = tracker.format_weekly_summary(args.person)
        log.info(summary)

    elif args.command == "nudge":
        nudge_obj = tracker.get_accountability_nudge(args.person)
        if nudge_obj:
            log.info(nudge_obj.message)
        else:
            log.info("%s is on track — no nudge needed.", args.person)

    elif args.command == "autodetect":
        results = tracker.auto_detect_habits()
        log.info("Auto-detection results: %s", results)

    else:
        parser.print_help()


if __name__ == "__main__":
    _cli()
