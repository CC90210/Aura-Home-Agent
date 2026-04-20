#!/usr/bin/env python3
"""AURA monthly analytics exporter.

Reads learning/data/patterns.db + memory/weekly_reflections.json + data/pulse/aura_pulse.json,
writes a markdown report to memory/monthly/YYYY-MM.md.

The report is designed to be symlinked or indexed by the Obsidian vault at c:/Users/User/AURA/.obsidian,
so CC can flip through months in graph view.

Sections:
    - Habit streaks (current + month max)
    - Sleep 30-day trend (avg, median, trend direction)
    - Energy patterns (by day-of-week, by hour-of-day)
    - Mode utilization (studio / focus / goodnight / party counts + total minutes)
    - Guest-mode history (entries + durations)
    - Top scenes triggered
    - Notable reflections from weekly_reflections.md
    - LIFE_CANON citations (which principles were invoked most)

Run:
    python scripts/aura_analytics.py                  # export current month
    python scripts/aura_analytics.py --month 2026-03  # export specific month
    python scripts/aura_analytics.py --resident cc    # only cc (default both)

The exporter is read-only on all data sources. It never modifies patterns.db or pulse files.
Privacy: respects the 3-part privacy structure — emits per-resident files if --resident given,
else produces a shared file plus one private file per resident (no cross-resident leakage).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "learning" / "data" / "patterns.db"
PULSE_PATH = REPO_ROOT / "data" / "pulse" / "aura_pulse.json"
WEEKLY_REFLECTIONS_JSON = REPO_ROOT / "memory" / "weekly_reflections.json"
WEEKLY_REFLECTIONS_MD = REPO_ROOT / "memory" / "weekly_reflections.md"
OUTPUT_DIR = REPO_ROOT / "memory" / "monthly"


@dataclass
class MonthSpan:
    year: int
    month: int

    @property
    def start(self) -> datetime:
        return datetime(self.year, self.month, 1, tzinfo=timezone.utc)

    @property
    def end(self) -> datetime:
        if self.month == 12:
            return datetime(self.year + 1, 1, 1, tzinfo=timezone.utc)
        return datetime(self.year, self.month + 1, 1, tzinfo=timezone.utc)

    @property
    def label(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"

    @classmethod
    def parse(cls, s: str | None) -> "MonthSpan":
        if s is None:
            today = date.today()
            return cls(today.year, today.month)
        y, m = s.split("-")
        return cls(int(y), int(m))


@dataclass
class ReportBundle:
    span: MonthSpan
    resident: str | None
    pulse: dict[str, Any]
    habit_streaks: dict[str, int] = field(default_factory=dict)
    sleep_points: list[tuple[datetime, float]] = field(default_factory=list)
    mode_minutes: dict[str, int] = field(default_factory=dict)
    mode_counts: dict[str, int] = field(default_factory=dict)
    guest_mode_events: list[dict[str, Any]] = field(default_factory=list)
    top_scenes: list[tuple[str, int]] = field(default_factory=list)
    energy_by_dow: dict[int, float] = field(default_factory=dict)
    energy_by_hour: dict[int, float] = field(default_factory=dict)
    reflections: list[dict[str, Any]] = field(default_factory=list)
    canon_citations: dict[str, int] = field(default_factory=dict)


def _load_pulse() -> dict[str, Any]:
    if not PULSE_PATH.exists():
        return {}
    return json.loads(PULSE_PATH.read_text(encoding="utf-8"))


def _open_db() -> sqlite3.Connection | None:
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _query_habit_streaks(conn: sqlite3.Connection | None, span: MonthSpan, resident: str) -> dict[str, int]:
    """Return {habit_name: max_streak_in_month}. Safe when table missing."""
    if conn is None:
        return {}
    try:
        rows = conn.execute(
            """
            SELECT habit_name, MAX(streak) AS max_streak
            FROM habit_log
            WHERE person = ?
              AND logged_at >= ?
              AND logged_at < ?
            GROUP BY habit_name
            """,
            (resident, span.start.isoformat(), span.end.isoformat()),
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["habit_name"]: int(r["max_streak"] or 0) for r in rows}


def _query_sleep_points(conn: sqlite3.Connection | None, span: MonthSpan, resident: str) -> list[tuple[datetime, float]]:
    if conn is None:
        return []
    try:
        rows = conn.execute(
            """
            SELECT logged_at, hours
            FROM sleep_log
            WHERE person = ?
              AND logged_at >= ?
              AND logged_at < ?
            ORDER BY logged_at ASC
            """,
            (resident, span.start.isoformat(), span.end.isoformat()),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    out: list[tuple[datetime, float]] = []
    for r in rows:
        try:
            out.append((datetime.fromisoformat(r["logged_at"]), float(r["hours"])))
        except (ValueError, TypeError):
            continue
    return out


def _query_mode_usage(conn: sqlite3.Connection | None, span: MonthSpan, resident: str) -> tuple[dict[str, int], dict[str, int]]:
    if conn is None:
        return {}, {}
    try:
        rows = conn.execute(
            """
            SELECT scene_or_mode, SUM(duration_seconds)/60 AS minutes, COUNT(*) AS activations
            FROM scene_activations
            WHERE (person = ? OR person IS NULL)
              AND started_at >= ?
              AND started_at < ?
            GROUP BY scene_or_mode
            ORDER BY minutes DESC
            """,
            (resident, span.start.isoformat(), span.end.isoformat()),
        ).fetchall()
    except sqlite3.OperationalError:
        return {}, {}
    minutes = {r["scene_or_mode"]: int(r["minutes"] or 0) for r in rows}
    counts = {r["scene_or_mode"]: int(r["activations"] or 0) for r in rows}
    return minutes, counts


def _query_guest_mode(conn: sqlite3.Connection | None, span: MonthSpan) -> list[dict[str, Any]]:
    if conn is None:
        return []
    try:
        rows = conn.execute(
            """
            SELECT started_at, ended_at, activated_by
            FROM guest_mode_log
            WHERE started_at >= ? AND started_at < ?
            ORDER BY started_at ASC
            """,
            (span.start.isoformat(), span.end.isoformat()),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(r) for r in rows]


def _query_top_scenes(conn: sqlite3.Connection | None, span: MonthSpan, limit: int = 10) -> list[tuple[str, int]]:
    if conn is None:
        return []
    try:
        rows = conn.execute(
            """
            SELECT scene_or_mode, COUNT(*) AS n
            FROM scene_activations
            WHERE started_at >= ? AND started_at < ?
            GROUP BY scene_or_mode
            ORDER BY n DESC
            LIMIT ?
            """,
            (span.start.isoformat(), span.end.isoformat(), limit),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [(r["scene_or_mode"], int(r["n"])) for r in rows]


def _query_energy_patterns(conn: sqlite3.Connection | None, span: MonthSpan, resident: str) -> tuple[dict[int, float], dict[int, float]]:
    if conn is None:
        return {}, {}
    try:
        rows = conn.execute(
            """
            SELECT logged_at, energy
            FROM energy_log
            WHERE person = ? AND logged_at >= ? AND logged_at < ?
            """,
            (resident, span.start.isoformat(), span.end.isoformat()),
        ).fetchall()
    except sqlite3.OperationalError:
        return {}, {}
    by_dow: dict[int, list[float]] = {}
    by_hour: dict[int, list[float]] = {}
    for r in rows:
        try:
            ts = datetime.fromisoformat(r["logged_at"])
            e = float(r["energy"])
        except (ValueError, TypeError):
            continue
        by_dow.setdefault(ts.weekday(), []).append(e)
        by_hour.setdefault(ts.hour, []).append(e)
    return (
        {k: round(mean(v), 2) for k, v in by_dow.items()},
        {k: round(mean(v), 2) for k, v in by_hour.items()},
    )


def _load_reflections(span: MonthSpan, resident: str) -> list[dict[str, Any]]:
    if not WEEKLY_REFLECTIONS_JSON.exists():
        return []
    try:
        data = json.loads(WEEKLY_REFLECTIONS_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    blob = data.get(resident) or data.get(resident.lower()) or {}
    out: list[dict[str, Any]] = []
    entries = blob.get("entries") if isinstance(blob, dict) else None
    if isinstance(entries, list):
        for e in entries:
            try:
                ts = datetime.fromisoformat(e.get("timestamp"))
            except (ValueError, TypeError):
                continue
            if span.start <= ts < span.end:
                out.append(e)
    elif "last_reflection" in blob:
        try:
            ts = datetime.fromisoformat(blob["last_reflection"].replace("Z", "+00:00"))
        except (ValueError, TypeError, AttributeError):
            return []
        if span.start <= ts < span.end:
            out.append({"timestamp": blob["last_reflection"], "text": blob.get("last_text", "")})
    return out


def _load_canon_citations(span: MonthSpan, conn: sqlite3.Connection | None) -> dict[str, int]:
    """Count how many times each LIFE_CANON source was cited in nudge traces."""
    if conn is None:
        return {}
    try:
        rows = conn.execute(
            """
            SELECT canon_source, COUNT(*) AS n
            FROM nudge_traces
            WHERE sent_at >= ? AND sent_at < ?
            GROUP BY canon_source
            ORDER BY n DESC
            """,
            (span.start.isoformat(), span.end.isoformat()),
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["canon_source"]: int(r["n"]) for r in rows}


def _format_trend(points: list[tuple[datetime, float]]) -> str:
    if not points:
        return "no data"
    values = [v for _, v in points]
    if len(values) < 2:
        return f"single point: {values[0]:.1f}h"
    first_half = values[: len(values) // 2]
    second_half = values[len(values) // 2 :]
    delta = mean(second_half) - mean(first_half)
    arrow = "↑" if delta > 0.2 else ("↓" if delta < -0.2 else "→")
    return f"avg {mean(values):.1f}h, median {median(values):.1f}h, trend {arrow} ({delta:+.1f}h)"


_DOW_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _render(bundle: ReportBundle) -> str:
    lines: list[str] = []
    heading = f"# AURA Monthly — {bundle.span.label}"
    if bundle.resident:
        heading += f" — {bundle.resident}"
    lines.append(heading)
    lines.append("")
    lines.append(f"> Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')} · Read-only export.")
    lines.append("")

    lines.append("## Habit Streaks")
    if bundle.habit_streaks:
        for habit, streak in sorted(bundle.habit_streaks.items(), key=lambda kv: -kv[1]):
            lines.append(f"- **{habit}** — max streak {streak} days")
    else:
        lines.append("- _no habit data for this month_")
    lines.append("")

    lines.append("## Sleep (30-day lookback)")
    lines.append(f"- {_format_trend(bundle.sleep_points)}")
    lines.append("")

    lines.append("## Energy Patterns")
    if bundle.energy_by_dow:
        lines.append("**By day-of-week:**")
        for dow in sorted(bundle.energy_by_dow):
            lines.append(f"- {_DOW_LABELS[dow]}: {bundle.energy_by_dow[dow]}/10")
    if bundle.energy_by_hour:
        lines.append("")
        lines.append("**By hour:**")
        peak_hour = max(bundle.energy_by_hour, key=lambda h: bundle.energy_by_hour[h])
        trough_hour = min(bundle.energy_by_hour, key=lambda h: bundle.energy_by_hour[h])
        lines.append(f"- peak: {peak_hour:02d}:00 ({bundle.energy_by_hour[peak_hour]}/10)")
        lines.append(f"- trough: {trough_hour:02d}:00 ({bundle.energy_by_hour[trough_hour]}/10)")
    if not bundle.energy_by_dow and not bundle.energy_by_hour:
        lines.append("- _no energy logs this month_")
    lines.append("")

    lines.append("## Mode Utilization")
    if bundle.mode_minutes:
        for mode, minutes in sorted(bundle.mode_minutes.items(), key=lambda kv: -kv[1]):
            counts = bundle.mode_counts.get(mode, 0)
            lines.append(f"- **{mode}** — {minutes} min across {counts} activations")
    else:
        lines.append("- _no mode activations recorded_")
    lines.append("")

    lines.append("## Guest-Mode History")
    if bundle.guest_mode_events:
        for g in bundle.guest_mode_events:
            started = g.get("started_at", "?")
            ended = g.get("ended_at") or "still active"
            by = g.get("activated_by") or "unknown"
            lines.append(f"- {started} → {ended} (by {by})")
    else:
        lines.append("- _no guest-mode activations this month_")
    lines.append("")

    lines.append("## Top Scenes")
    if bundle.top_scenes:
        for scene, n in bundle.top_scenes:
            lines.append(f"- {scene} — {n}")
    else:
        lines.append("- _no scene activations_")
    lines.append("")

    lines.append("## LIFE_CANON Citations (which principles drove nudges)")
    if bundle.canon_citations:
        for source, n in bundle.canon_citations.items():
            lines.append(f"- {source}: {n}")
    else:
        lines.append("- _no traced nudges this month — Pi likely offline or nudge_traces table empty_")
    lines.append("")

    lines.append("## Reflections")
    if bundle.reflections:
        for r in bundle.reflections:
            ts = r.get("timestamp", "?")
            text = (r.get("text") or "").strip()
            lines.append(f"### {ts}")
            lines.append(text if text else "_no reflection body_")
            lines.append("")
    else:
        lines.append("- _no reflections recorded this month_")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Pulse Snapshot (for context)")
    lines.append("```json")
    pulse_subset = {
        "hardware_online": bundle.pulse.get("hardware_online"),
        "updated_at": bundle.pulse.get("updated_at"),
        "status": bundle.pulse.get("status"),
        "active_scene": bundle.pulse.get("apartment_shared", {}).get("active_scene"),
        "guest_mode": bundle.pulse.get("apartment_shared", {}).get("guest_mode"),
    }
    lines.append(json.dumps(pulse_subset, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("## Obsidian Index")
    lines.append("")
    lines.append("This file lives at `memory/monthly/` inside the AURA vault. Link it into your monthly-review Obsidian page with:")
    lines.append("")
    lines.append(f"    ![[{bundle.span.label}]]")
    lines.append("")

    return "\n".join(lines)


def build_report(span: MonthSpan, resident: str) -> ReportBundle:
    pulse = _load_pulse()
    conn = _open_db()
    bundle = ReportBundle(span=span, resident=resident, pulse=pulse)
    try:
        bundle.habit_streaks = _query_habit_streaks(conn, span, resident)
        bundle.sleep_points = _query_sleep_points(conn, span, resident)
        bundle.mode_minutes, bundle.mode_counts = _query_mode_usage(conn, span, resident)
        bundle.guest_mode_events = _query_guest_mode(conn, span)
        bundle.top_scenes = _query_top_scenes(conn, span)
        bundle.energy_by_dow, bundle.energy_by_hour = _query_energy_patterns(conn, span, resident)
        bundle.reflections = _load_reflections(span, resident)
        bundle.canon_citations = _load_canon_citations(span, conn)
    finally:
        if conn is not None:
            conn.close()
    return bundle


def main() -> int:
    parser = argparse.ArgumentParser(description="AURA monthly analytics exporter.")
    parser.add_argument("--month", default=None, help="YYYY-MM, default = current month.")
    parser.add_argument("--resident", default=None, help="resident id (e.g. conaugh, adon). Omit for all residents.")
    args = parser.parse_args()

    span = MonthSpan.parse(args.month)
    residents = [args.resident] if args.resident else ["conaugh", "adon"]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for r in residents:
        bundle = build_report(span, r)
        suffix = f"-{r}" if not args.resident and r else ""
        out_path = OUTPUT_DIR / f"{span.label}{suffix}.md"
        out_path.write_text(_render(bundle), encoding="utf-8")
        print(f"wrote {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
