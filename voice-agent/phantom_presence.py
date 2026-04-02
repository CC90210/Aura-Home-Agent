"""
AURA Phantom Presence 2.0 — Intelligent Away Simulation
=========================================================
Instead of randomly toggling lights (the dumb version in the static HA script),
Phantom Presence replays your *actual* patterns from the past week when you're
away.  The result is a simulation that looks exactly like how you actually live
— because it is.

How it works
------------
1. ``generate_simulation_schedule`` queries the PatternEngine's event history
   for the last 7 days, filtering to ``light.*`` and ``switch.*`` state changes.
2. Events are grouped by (hour, day_of_week).  The current weekday and time are
   matched against last week's same slot.
3. For the next N hours, a schedule is built that mirrors what actually happened
   at those times last week, with ±10 minute jitter so the pattern is not
   machine-predictable from the outside.
4. ``create_ha_script`` converts the schedule to a Home Assistant script YAML
   that can be called by Away Mode or pasted into HA's script editor.
5. ``get_typical_evening`` returns a human-readable summary of an average
   evening for dashboard display and the weekly briefing.

Design decisions
----------------
- Random jitter (±10 min) is applied via Python's ``random`` module seeded with
  the current date so repeated calls on the same day produce the same schedule
  (deterministic within a day, different day-to-day).
- The PatternEngine dependency is injected so this class can be tested with a
  mock engine.  It does NOT import from ``learning.pattern_engine`` directly to
  keep the voice-agent package loosely coupled to the learning package.
- HA script YAML is emitted as a plain string.  The caller is responsible for
  writing it to the correct HA config path and calling a HA restart or
  ``script.reload`` service.
- If the PatternEngine has no data (new install), a safe, minimal hardcoded
  schedule is used as a fallback so Away Mode still has something to work with.

Integration
-----------
Away Mode automation calls ``script.presence_simulation``.
When PhantomPresence has enough data (>= 7 days of events), the caller should:
  1. Call ``generate_simulation_schedule()`` on departure.
  2. Call ``create_ha_script(schedule)`` to get the YAML.
  3. Write the YAML to ``/config/scripts/presence_simulation.yaml`` on the Pi.
  4. Call HA service ``script.reload`` to activate it.

On first use (< 7 days of data) the static fallback script remains active.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Optional, Protocol

import yaml

log = logging.getLogger("aura.phantom_presence")

# ---------------------------------------------------------------------------
# Protocol — loose typing for PatternEngine dependency
# ---------------------------------------------------------------------------
# Using a Protocol lets us type-check without importing PatternEngine directly,
# keeping the voice-agent and learning packages independently deployable.


class _PatternEngineProtocol(Protocol):
    """Minimal interface expected from PatternEngine."""

    def get_patterns(
        self,
        entity_id: str,
        day_of_week: Optional[int] = None,
        time_range: Optional[tuple[int, int]] = None,
    ) -> list[Any]:
        ...

    # The _db attribute is used to run raw queries when no structured API exists.
    # Accessing private attributes across packages is acceptable here because
    # PhantomPresence is a sibling system, not a public consumer.
    _db: Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maximum random jitter in minutes applied to each scheduled action.
_JITTER_MINUTES = 10

# Domains to replay.
_REPLAY_DOMAINS = frozenset({"light", "switch"})

# Minimum number of historical events required before we trust the data enough
# to use real patterns instead of the static fallback.
_MIN_EVENTS_FOR_REAL_PATTERNS = 20

# Default evening pattern used as a fallback when no data is available.
_FALLBACK_EVENING: list[dict[str, Any]] = [
    {
        "time": "18:30",
        "entity": "light.living_room_leds",
        "action": "turn_on",
        "data": {"brightness_pct": 60, "color_temp_kelvin": 3000},
    },
    {
        "time": "19:15",
        "entity": "light.bedroom_leds",
        "action": "turn_on",
        "data": {"brightness_pct": 40, "color_temp_kelvin": 2700},
    },
    {
        "time": "20:45",
        "entity": "light.living_room_leds",
        "action": "turn_off",
        "data": {},
    },
    {
        "time": "22:00",
        "entity": "light.bedroom_leds",
        "action": "turn_off",
        "data": {},
    },
]


# ---------------------------------------------------------------------------
# PhantomPresence
# ---------------------------------------------------------------------------


class PhantomPresence:
    """
    Generates intelligent away-mode simulations based on real usage patterns.

    Parameters
    ----------
    pattern_engine:
        A PatternEngine instance (or compatible mock).  Used to query the
        historical event log and entity-level pattern records.
    """

    def __init__(self, pattern_engine: _PatternEngineProtocol) -> None:
        self._engine = pattern_engine
        log.info("PhantomPresence initialised.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_simulation_schedule(self, hours: int = 6) -> list[dict[str, Any]]:
        """
        Build a time-ordered simulation schedule for the next ``hours`` hours
        based on last week's actual light and switch events.

        Parameters
        ----------
        hours:
            How many hours ahead to simulate.  Default is 6 (a typical evening
            away from home).

        Returns
        -------
        list[dict]
            Time-ordered list of timed actions:
            ``[{"time": "19:15", "entity": "light.living_room_leds",
                "action": "turn_on", "data": {"brightness_pct": 70, ...}}, ...]``

            Returns a safe fallback schedule if there is insufficient history.
        """
        now = datetime.now(timezone.utc)
        # Seed RNG with today's date for determinism within a day
        rng = random.Random(now.date().toordinal())

        raw_events = self._fetch_last_week_events()

        if len(raw_events) < _MIN_EVENTS_FOR_REAL_PATTERNS:
            log.warning(
                "Insufficient event history (%d events, need %d) — "
                "using fallback simulation schedule.",
                len(raw_events),
                _MIN_EVENTS_FOR_REAL_PATTERNS,
            )
            return self._apply_jitter(_FALLBACK_EVENING, rng)

        schedule: list[dict[str, Any]] = []

        for offset_minutes in range(0, hours * 60, 15):
            target_dt = now + timedelta(minutes=offset_minutes)
            target_hour = target_dt.hour
            # Match against same day-of-week last week
            target_dow = target_dt.weekday()

            matching = [
                e for e in raw_events
                if e["hour"] == target_hour and e["day_of_week"] == target_dow
                and e["domain"] in _REPLAY_DOMAINS
            ]

            for event in matching:
                # Apply ±10 minute jitter to the exact time
                base_dt = target_dt.replace(minute=0, second=0, microsecond=0)
                jitter = rng.randint(-_JITTER_MINUTES, _JITTER_MINUTES)
                action_dt = base_dt + timedelta(minutes=jitter)

                entry: dict[str, Any] = {
                    "time": action_dt.strftime("%H:%M"),
                    "entity": event["entity_id"],
                    "action": event["action"],
                    "data": event.get("data", {}),
                }
                schedule.append(entry)

        if not schedule:
            log.warning(
                "Pattern matching returned no events for the next %d hours "
                "— using fallback schedule.",
                hours,
            )
            return self._apply_jitter(_FALLBACK_EVENING, rng)

        # Sort by time and deduplicate entity actions within the same minute
        schedule.sort(key=lambda x: x["time"])
        schedule = self._deduplicate(schedule)

        log.info(
            "Simulation schedule generated: %d actions over %d hours.",
            len(schedule),
            hours,
        )
        return schedule

    def create_ha_script(self, schedule: list[dict[str, Any]]) -> str:
        """
        Convert a simulation schedule into a Home Assistant script YAML string.

        The output is a single script called ``presence_simulation`` that can
        be written to ``/config/scripts/presence_simulation.yaml`` on the Pi
        and reloaded without a full HA restart.

        Parameters
        ----------
        schedule:
            List of timed action dicts as returned by
            ``generate_simulation_schedule``.

        Returns
        -------
        str
            Valid HA script YAML.

        Example output (abbreviated)::

            presence_simulation:
              alias: "Presence Simulation (PhantomPresence 2.0)"
              sequence:
                - delay: "00:12:00"
                - service: light.turn_on
                  target:
                    entity_id: light.living_room_leds
                  data:
                    brightness_pct: 60
                    color_temp_kelvin: 3000
                  continue_on_error: true
        """
        if not schedule:
            return yaml.dump(
                {
                    "presence_simulation": {
                        "alias": "Presence Simulation (PhantomPresence 2.0 — no data)",
                        "sequence": [],
                    }
                },
                default_flow_style=False,
                allow_unicode=True,
            )

        now = datetime.now(timezone.utc)
        sequence: list[dict[str, Any]] = []
        prev_time: Optional[str] = None

        for action in schedule:
            action_time_str = action["time"]
            # Compute delay from previous action (or from now for the first action)
            if prev_time is None:
                try:
                    action_hour, action_min = map(int, action_time_str.split(":"))
                    action_dt = now.replace(
                        hour=action_hour, minute=action_min, second=0, microsecond=0
                    )
                    delay_seconds = max(0, int((action_dt - now).total_seconds()))
                except (ValueError, OverflowError):
                    delay_seconds = 0
            else:
                prev_h, prev_m = map(int, prev_time.split(":"))
                cur_h, cur_m = map(int, action_time_str.split(":"))
                delay_seconds = max(0, (cur_h * 60 + cur_m - prev_h * 60 - prev_m) * 60)

            # Delay step
            delay_str = _seconds_to_ha_delay(delay_seconds)
            if delay_seconds > 0:
                sequence.append({"delay": delay_str})

            # Service call step
            domain = action["entity"].split(".")[0]
            service_step: dict[str, Any] = {
                "service": f"{domain}.{action['action']}",
                "target": {"entity_id": action["entity"]},
                "continue_on_error": True,
            }
            if action.get("data"):
                service_step["data"] = action["data"]

            sequence.append(service_step)
            prev_time = action_time_str

        # Final cleanup — turn everything off
        sequence.append(
            {
                "service": "light.turn_off",
                "target": {
                    "entity_id": [
                        "light.living_room_leds",
                        "light.bedroom_leds",
                        "light.overhead",
                    ]
                },
                "continue_on_error": True,
            }
        )

        script_dict = {
            "presence_simulation": {
                "alias": "Presence Simulation (PhantomPresence 2.0)",
                "description": (
                    "Dynamic simulation generated by PhantomPresence from "
                    f"real usage patterns. Generated: {now.strftime('%Y-%m-%d %H:%M UTC')}"
                ),
                "mode": "single",
                "sequence": sequence,
            }
        }

        return yaml.dump(
            script_dict,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

    def get_typical_evening(self) -> dict[str, Any]:
        """
        Return a plain-language summary of what a typical evening looks like
        based on historical light and switch patterns.

        Used by the dashboard's away-mode preview card and the Energy Oracle
        weekly brief.

        Returns
        -------
        dict with keys:
          - ``lights_on_at``        (str)  — typical time lights come on, e.g. "6:30 PM"
          - ``lights_off_at``       (str)  — typical time lights go off, e.g. "10:15 PM"
          - ``most_active_room``    (str)  — entity area with most events
          - ``typical_duration_h``  (float)— average hours lights are on per evening
          - ``description``         (str)  — natural language summary for TTS / display
          - ``data_days``           (int)  — number of days of history behind the summary
        """
        raw_events = self._fetch_last_week_events(days=14)
        evening_events = [
            e for e in raw_events
            if 17 <= e["hour"] <= 23
            and e["domain"] == "light"
        ]

        if not evening_events:
            return {
                "lights_on_at": "6:30 PM",
                "lights_off_at": "10:30 PM",
                "most_active_room": "Living Room",
                "typical_duration_h": 4.0,
                "description": (
                    "Not enough data yet to model a typical evening. "
                    "After a week of normal use, I'll have a real picture for you."
                ),
                "data_days": 0,
            }

        # First typical light-on event in the evening window
        on_events = sorted(
            [e for e in evening_events if e["action"] == "turn_on"],
            key=lambda x: x["hour"],
        )
        first_on_hour = on_events[0]["hour"] if on_events else 18
        lights_on_at = _fmt_hour(first_on_hour)

        # Last typical light-off event
        off_events = sorted(
            [e for e in evening_events if e["action"] == "turn_off"],
            key=lambda x: x["hour"],
            reverse=True,
        )
        last_off_hour = off_events[0]["hour"] if off_events else 22
        lights_off_at = _fmt_hour(last_off_hour)

        # Most active room by entity event count
        room_counts: dict[str, int] = {}
        for e in evening_events:
            room = _entity_to_room(e["entity_id"])
            room_counts[room] = room_counts.get(room, 0) + 1
        most_active_room = max(room_counts, key=room_counts.__getitem__) if room_counts else "Living Room"

        typical_duration_h = max(0.5, last_off_hour - first_on_hour)
        data_days = len(set(e.get("date", "") for e in raw_events if e.get("date")))

        description = (
            f"On a typical evening lights come on around {lights_on_at} "
            f"and go off around {lights_off_at}. "
            f"Most activity is in the {most_active_room}."
        )

        return {
            "lights_on_at": lights_on_at,
            "lights_off_at": lights_off_at,
            "most_active_room": most_active_room,
            "typical_duration_h": round(typical_duration_h, 1),
            "description": description,
            "data_days": data_days,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _fetch_last_week_events(self, days: int = 7) -> list[dict[str, Any]]:
        """
        Query the pattern engine's database for light.* and switch.* events
        from the last ``days`` days.

        Returns a list of dicts with keys:
          ``entity_id``, ``action``, ``hour``, ``day_of_week``, ``domain``,
          ``data``, ``date``.
        """
        from datetime import date

        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        try:
            rows = self._engine._db.execute(
                """
                SELECT entity_id, new_state, timestamp
                  FROM events
                 WHERE (entity_id LIKE 'light.%' OR entity_id LIKE 'switch.%')
                   AND new_state IN ('on', 'off')
                   AND timestamp >= ?
                 ORDER BY timestamp ASC
                """,
                (cutoff,),
            )
        except Exception as exc:  # noqa: BLE001
            log.error("Failed to fetch events from PatternEngine DB: %s", exc)
            return []

        processed: list[dict[str, Any]] = []
        for row in rows:
            try:
                ts = datetime.fromisoformat(row["timestamp"])
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                entity_id: str = row["entity_id"]
                domain = entity_id.split(".")[0]
                action = "turn_on" if row["new_state"] == "on" else "turn_off"

                processed.append(
                    {
                        "entity_id": entity_id,
                        "action": action,
                        "hour": ts.hour,
                        "day_of_week": ts.weekday(),
                        "domain": domain,
                        "date": ts.date().isoformat(),
                        "data": _default_light_data(entity_id, action),
                    }
                )
            except (ValueError, KeyError, AttributeError) as exc:
                log.debug("Skipping malformed event row: %s — %s", row, exc)
                continue

        log.debug("Fetched %d light/switch events from last %d days.", len(processed), days)
        return processed

    @staticmethod
    def _apply_jitter(
        schedule: list[dict[str, Any]], rng: random.Random
    ) -> list[dict[str, Any]]:
        """Apply ±10 minute random jitter to each entry's time field."""
        jittered: list[dict[str, Any]] = []
        for entry in schedule:
            h, m = map(int, entry["time"].split(":"))
            offset = rng.randint(-_JITTER_MINUTES, _JITTER_MINUTES)
            total_minutes = max(0, min(23 * 60 + 59, h * 60 + m + offset))
            new_h, new_m = divmod(total_minutes, 60)
            jittered.append({**entry, "time": f"{new_h:02d}:{new_m:02d}"})
        return sorted(jittered, key=lambda x: x["time"])

    @staticmethod
    def _deduplicate(schedule: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Remove duplicate actions for the same entity within the same minute,
        keeping the last entry (most recent overwrites earlier in the same slot).
        """
        seen: dict[tuple[str, str], int] = {}  # (entity, time) → index
        result: list[dict[str, Any]] = []
        for entry in schedule:
            key = (entry["entity"], entry["time"])
            if key in seen:
                result[seen[key]] = entry  # overwrite
            else:
                seen[key] = len(result)
                result.append(entry)
        return result


# ---------------------------------------------------------------------------
# Internal utilities
# ---------------------------------------------------------------------------


def _seconds_to_ha_delay(seconds: int) -> str:
    """Convert an integer number of seconds to HA delay format HH:MM:SS."""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def _fmt_hour(hour: int) -> str:
    """Format a 24-hour integer as a human-readable label, e.g. 19 → '7 PM'."""
    if hour == 0:
        return "12 AM"
    if hour < 12:
        return f"{hour} AM"
    if hour == 12:
        return "12 PM"
    return f"{hour - 12} PM"


def _entity_to_room(entity_id: str) -> str:
    """
    Extract a human-readable room name from an entity ID.

    e.g. ``light.living_room_leds`` → ``"Living Room"``
         ``light.bedroom_leds``     → ``"Bedroom"``
    """
    parts = entity_id.split(".")
    if len(parts) < 2:
        return "Unknown"
    name_part = parts[1]
    # Strip common suffixes
    for suffix in ("_leds", "_lights", "_lamp", "_overhead", "_strip"):
        name_part = name_part.replace(suffix, "")
    return name_part.replace("_", " ").title()


def _default_light_data(entity_id: str, action: str) -> dict[str, Any]:
    """
    Return sensible default light data for replay when the original attribute
    data is not stored in the events table.
    """
    if action == "turn_off":
        return {}
    # Bedroom: warmer and dimmer; everything else: medium warm
    if "bedroom" in entity_id:
        return {"brightness_pct": 30, "color_temp_kelvin": 2700}
    return {"brightness_pct": 60, "color_temp_kelvin": 3000}
