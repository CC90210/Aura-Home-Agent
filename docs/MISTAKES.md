# AURA Agent Mistakes Log

This file records bugs introduced or found by the AI agent during codebase work.
Format: BUG-NNN, file, root cause, fix, prevention.

---

## BUG-001 — TypeError: `timeout` kwarg on `messages.create()`

**File:** `voice-agent/intent_handler.py`
**Severity:** CRITICAL — crashes every voice command
**Date:** 2026-04-03

**Root Cause:**
`timeout=30.0` was passed as a keyword argument to `self._client.messages.create()`. The Anthropic Python SDK does not accept `timeout` on the `create()` method — it is a client-level parameter that must be set on the `Anthropic()` constructor. This caused a `TypeError` on every single Claude API call, making the entire voice pipeline non-functional.

**Fix:**
Removed `timeout=30.0` from `messages.create()`. Added `timeout=30.0` to `anthropic.Anthropic(api_key=anthropic_api_key, timeout=30.0)` at client construction time.

**Prevention:**
When using the Anthropic SDK, always set `timeout`, `max_retries`, and other transport-level options on the `Anthropic()` client constructor, not on individual method calls. Check SDK docs before adding kwargs to `create()`.

---

## BUG-003 — `EnergyOracle` crashes with `AttributeError` when `habit_tracker` or `content_radar` is None

**File:** `voice-agent/energy_oracle.py` — `__init__`, `get_weekly_data`, `_get_habit_summary`
**Severity:** CRITICAL — crashes EnergyOracle init or weekly brief generation when learning features are partially unavailable
**Date:** 2026-04-03

**Root Cause:**
`EnergyOracle.__init__` declared `habit_tracker` and `content_radar` as required positional parameters typed with Protocol types (no `Optional`, no default). The calling code in `aura_voice.py` explicitly passes `self._habit_tracker` and `self._content_radar` which may both be `None` (e.g. if the learning package failed to load), commenting "EnergyOracle handles gracefully". But `EnergyOracle` did not guard against `None`: `_get_habit_summary` called `self._habit_tracker.get_weekly_report(person)` unconditionally, and `get_weekly_data` called `self._content_radar.get_content_stats(person)` unconditionally — both would `AttributeError` on `NoneType`.

**Fix:**
Made both parameters `Optional` with `None` defaults in the signature. Added a `None` guard in `_get_habit_summary` returning an empty summary dict. Moved `content_radar` thread creation inside a `if self._content_radar is not None:` guard in `get_weekly_data`.

**Prevention:**
When a docstring or call-site comment says a parameter "may be None" or "handled gracefully", verify the implementation actually has None guards before every attribute access. Never assume Protocol-typed parameters are non-None without runtime checks.

---

## BUG-004 — `default_speaker` undefined NameError silently disables VibeSync and SocialSonar

**File:** `voice-agent/aura_voice.py` — `_init_features()`
**Severity:** HIGH — silently disables VibeSync and SocialSonar even when their imports succeed
**Date:** 2026-04-03

**Root Cause:**
`default_speaker` was assigned inside the `GhostDJ` try block. When GhostDJ fails to import (`GhostDJ is None`), it raises immediately and `default_speaker` is never assigned. The subsequent `VibeSync` try block references `default_speaker` on the very next line — causing a `NameError` that is silently caught by the except clause, disabling VibeSync. `SocialSonar` had the same issue further down.

**Fix:**
Moved the `default_speaker` resolution to the top of `_init_features()`, before any try block, so it is always available regardless of which feature modules succeed or fail.

**Prevention:**
Variables used across multiple try/except blocks must be defined before the first try block. Never rely on a variable that is only assigned inside a try block being available outside it — the except clause may have swallowed the assignment.

---

## BUG-002 — `content_radar` feature response silently never set

**File:** `voice-agent/intent_handler.py` — `_execute_feature_command()`, content_radar branch
**Severity:** MEDIUM — silent failure, wrong TTS response
**Date:** 2026-04-03

**Root Cause:**
The `content_radar` branch checked `isinstance(stats, str)` to decide whether to set `self._feature_response`. However, `ContentRadar.get_content_stats()` returns a `dict`, not a `str`. The isinstance check was always `False`, so `_feature_response` was never populated. AURA would speak Claude's generic fallback instead of the actual content statistics.

**Fix:**
Changed check to `isinstance(stats, dict)`. Added a TTS-friendly string builder that extracts `total_sessions`, `days_since_last_session`, `average_session_length`, and `most_used_mode` from the dict and formats them into a speakable sentence. Kept `elif isinstance(stats, str)` as a fallback for any future string-returning path.

**Prevention:**
Before writing isinstance checks on return values, read the source of the method being called and verify its actual return type. Do not assume string — check the method signature and return statement directly.

