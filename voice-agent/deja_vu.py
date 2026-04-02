"""
AURA Deja Vu — Predictive Scene Activation
===========================================
Deja Vu makes AURA feel like the apartment read your mind.  It learns which
scenes you activate at which times on which days, and quietly sets them up
before you ask.

Design principles
-----------------
- *Subtle, not aggressive.*  The apartment gently sets things up.  It does
  not announce how smart it is.  If the user notices and thinks "huh, how did
  it know?" that is the perfect outcome.  If they feel surveilled, that is a
  failure.
- *Confidence-gated.*  A prediction is only acted on when the pattern engine
  reports high confidence (default 0.75).  Low-confidence guesses are silently
  discarded.
- *Rejection-aware.*  If a user overrides a prediction within 5 minutes, the
  rejection is recorded and fed back to the pattern engine.  Deja Vu will not
  keep suggesting the same scene that was just dismissed.
- *Non-interrupting.*  Deja Vu never interrupts an explicit scene choice.  If
  the user already activated a scene, predictions are skipped entirely.

Architecture
------------
``DejaVu`` is a dependency-injected service object.  It receives a reference
to the ``PatternEngine`` from the learning module so it can read learned
patterns and write feedback without owning a database connection itself.

It also receives an HA REST API client (url + token) so it can:
  1. Check which scene (if any) is currently active via input_boolean states.
  2. Activate a predicted scene via scene.turn_on.

The caller (voice agent or a scheduler daemon) is responsible for calling
``maybe_predict_and_activate()`` at appropriate intervals — typically on
presence-detected entry events and on a lightweight periodic poll (5–10 min).

Dependencies
------------
- ``learning.pattern_engine.PatternEngine``  (passed at construction)
- ``requests``
- Environment variables: ``HA_URL``, ``HA_TOKEN``
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

import requests

if TYPE_CHECKING:
    # Avoid a hard circular import — PatternEngine is always passed in at
    # runtime, so we only need the type at static analysis time.
    from learning.pattern_engine import PatternEngine

log = logging.getLogger("aura.deja_vu")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default confidence threshold (0.0 – 1.0).  Predictions below this level are
# silently dropped.
_DEFAULT_CONFIDENCE_THRESHOLD: float = 0.75

# Window (in hours, inclusive) to look for scene patterns around the current hour.
# ±1 hour: we look at the slot just before and the slot after to smooth sparse data.
_PATTERN_HOUR_WINDOW: int = 1

# How long (seconds) after a prediction was made before a lack of override is
# treated as implicit acceptance and fed back as positive evidence.
_ACCEPTANCE_WINDOW_SECONDS: int = 600  # 10 minutes

# How long (seconds) within which an override counts as an explicit rejection.
_REJECTION_WINDOW_SECONDS: int = 300  # 5 minutes

# How long (seconds) a rejected scene stays suppressed in the rejection cache.
_REJECTION_SUPPRESS_SECONDS: int = 3600  # 1 hour

# HA entity IDs: input_boolean per scene that tracks whether that mode is active.
# DejaVu reads these to decide if a scene is already active, and to detect
# user overrides (a prediction is rejected when a *different* mode turns on
# within the rejection window).
_SCENE_BOOLEAN_MAP: dict[str, str] = {
    "focus_mode":     "input_boolean.focus_mode_active",
    "studio_mode":    "input_boolean.studio_mode_active",
    "movie_mode":     "input_boolean.movie_mode_active",
    "gaming_mode":    "input_boolean.gaming_mode_active",
    "streaming_mode": "input_boolean.streaming_mode_active",
    "podcast_mode":   "input_boolean.podcast_mode_active",
    "party_mode":     "input_boolean.party_mode_active",
    "workout_mode":   "input_boolean.workout_mode_active",
    "guest_mode":     "input_boolean.guest_mode_active",
    "away_mode":      "input_boolean.away_mode_active",
    "music_mode":     "input_boolean.music_mode_active",
    "welcome_home":   "input_boolean.welcome_home_active",
}

# HA scene entity IDs.  These are called when a prediction is activated.
_SCENE_ENTITY_MAP: dict[str, str] = {
    "focus_mode":     "scene.focus_mode",
    "studio_mode":    "scene.studio_mode",
    "movie_mode":     "scene.movie_mode",
    "gaming_mode":    "scene.gaming_mode",
    "streaming_mode": "scene.streaming_mode",
    "podcast_mode":   "scene.podcast_mode",
    "party_mode":     "scene.party_mode",
    "workout_mode":   "scene.workout_mode",
    "guest_mode":     "scene.guest_mode",
    "away_mode":      "scene.away_mode",
    "music_mode":     "scene.music_mode",
    "welcome_home":   "scene.welcome_home",
}

# Subtle announcement templates per scene.
# These are spoken aloud via TTS.  The key design rule: sound natural and
# offhand, NOT like an AI bragging about its predictive model.
_SCENE_ANNOUNCEMENTS: dict[str, str] = {
    "focus_mode":     "Set up your focus environment — lights and lo-fi ready.",
    "studio_mode":    "Studio's set up for you.",
    "movie_mode":     "Dimmed it down — looks like movie time.",
    "gaming_mode":    "Gaming setup is ready.",
    "streaming_mode": "Streaming setup is ready when you are.",
    "podcast_mode":   "Podcast environment is set.",
    "party_mode":     "Party mode loaded up.",
    "workout_mode":   "Workout lights are on. Let's go.",
    "guest_mode":     "Got the place looking right for company.",
    "away_mode":      "Buttoned up the apartment for you.",
    "music_mode":     "Music mode is on.",
    "welcome_home":   "Welcome back.",
}

# The PatternEngine records scene activations with this event_type.
_SCENE_EVENT_TYPE: str = "scene_activated"

# The entity_id prefix used when recording scene activations to the DB.
_SCENE_ENTITY_PREFIX: str = "scene."


# ---------------------------------------------------------------------------
# Prediction dataclass
# ---------------------------------------------------------------------------


class _Prediction:
    """
    Holds the state of a single in-flight prediction.

    Not exported — internal bookkeeping only.
    """

    __slots__ = (
        "prediction_id",
        "scene",
        "confidence",
        "reason",
        "person",
        "activated_at",
        "resolved",
    )

    def __init__(
        self,
        scene: str,
        confidence: float,
        reason: str,
        person: str,
    ) -> None:
        self.scene: str = scene
        self.confidence: float = confidence
        self.reason: str = reason
        self.person: str = person
        self.activated_at: float = time.monotonic()
        self.resolved: bool = False

        # Deterministic ID based on content + activation time so callers can
        # reference a specific prediction without us exposing internal state.
        raw = f"{scene}:{person}:{self.activated_at}"
        self.prediction_id: str = hashlib.sha1(  # noqa: S324 — not security-critical
            raw.encode(), usedforsecurity=False
        ).hexdigest()[:12]

    @property
    def age_seconds(self) -> float:
        return time.monotonic() - self.activated_at


# ---------------------------------------------------------------------------
# DejaVu
# ---------------------------------------------------------------------------


class DejaVu:
    """
    Predictive scene activation — activates scenes before the user asks.

    Parameters
    ----------
    pattern_engine:
        A live ``PatternEngine`` instance from ``learning.pattern_engine``.
        Used for reading patterns and writing feedback.
    ha_url:
        Base URL of the Home Assistant instance.
    ha_token:
        Long-lived access token for the HA REST API.
    config:
        Optional configuration overrides.  Supported keys:
          - ``confidence_threshold``  (float, default 0.75)
          - ``acceptance_window``     (int seconds, default 600)
          - ``rejection_window``      (int seconds, default 300)
          - ``rejection_suppress``    (int seconds, default 3600)
          - ``enabled``               (bool, default True)
    """

    def __init__(
        self,
        pattern_engine: "PatternEngine",
        ha_url: str,
        ha_token: str,
        config: dict[str, Any] | None = None,
    ) -> None:
        if not ha_token:
            raise ValueError("ha_token must not be empty.")

        self._pattern_engine = pattern_engine
        self._ha_url: str = ha_url.rstrip("/")
        self._ha_headers: dict[str, str] = {
            "Authorization": f"Bearer {ha_token}",
            "Content-Type": "application/json",
        }

        cfg = config or {}
        self._enabled: bool = bool(cfg.get("enabled", True))
        self._confidence_threshold: float = float(
            cfg.get("confidence_threshold", _DEFAULT_CONFIDENCE_THRESHOLD)
        )
        self._acceptance_window: int = int(
            cfg.get("acceptance_window", _ACCEPTANCE_WINDOW_SECONDS)
        )
        self._rejection_window: int = int(
            cfg.get("rejection_window", _REJECTION_WINDOW_SECONDS)
        )
        self._rejection_suppress: int = int(
            cfg.get("rejection_suppress", _REJECTION_SUPPRESS_SECONDS)
        )

        # { scene_name: monotonic timestamp of last rejection }
        self._rejection_cache: dict[str, float] = {}

        # Active in-flight prediction awaiting resolution feedback.
        # Only one prediction is tracked at a time — once resolved or expired,
        # the slot is cleared for the next prediction.
        self._active_prediction: _Prediction | None = None

        log.info(
            "DejaVu initialised — enabled=%s  confidence_threshold=%.2f",
            self._enabled,
            self._confidence_threshold,
        )

    # ------------------------------------------------------------------
    # Public control API
    # ------------------------------------------------------------------

    def enable(self) -> str:
        """
        Activate Deja Vu predictive activation.

        Returns
        -------
        str
            Confirmation message suitable for TTS.
        """
        self._enabled = True
        log.info("DejaVu enabled.")
        return "I'll start setting things up before you ask. You probably won't even notice."

    def disable(self) -> str:
        """
        Deactivate Deja Vu.  The pattern engine continues recording events
        in the background so learning is not interrupted.

        Returns
        -------
        str
            Confirmation message suitable for TTS.
        """
        self._enabled = False
        self._active_prediction = None
        log.info("DejaVu disabled.")
        return "Predictive mode off. I'll wait for you to tell me what you need."

    # ------------------------------------------------------------------
    # Prediction pipeline
    # ------------------------------------------------------------------

    def maybe_predict_and_activate(
        self, person: str, context: dict[str, Any] | None = None
    ) -> str | None:
        """
        Convenience wrapper that runs the full predict → validate → activate
        pipeline in one call.

        This is the primary entry point for the voice agent and scheduler
        daemon.  Call it on presence-detected entries and on a periodic
        lightweight poll (recommended every 5–10 minutes).

        Parameters
        ----------
        person:
            Resident ID (``"conaugh"`` / ``"adon"``).
        context:
            Optional context dict with keys: ``day_of_week`` (int 0–6),
            ``hour`` (int 0–23), ``activity`` (str).  When None the current
            system time is used.

        Returns
        -------
        str | None
            The TTS announcement if a scene was activated, otherwise ``None``.
        """
        if not self._enabled:
            return None

        # Resolve pending prediction feedback before issuing a new one
        self._maybe_resolve_pending()

        ctx = self._build_context(context)
        prediction = self.predict_next_scene(person, ctx)
        if prediction is None:
            return None

        if not self.should_activate(prediction):
            return None

        return self.activate_prediction(prediction, person)

    def predict_next_scene(
        self, person: str, context: dict[str, Any]
    ) -> dict[str, Any] | None:
        """
        Query the PatternEngine for scene activations that consistently happen
        at the current time and context, and return the most likely prediction.

        Parameters
        ----------
        person:
            Resident ID (``"conaugh"`` / ``"adon"``).
        context:
            Dict with keys:
              - ``day_of_week``  (int 0–6)
              - ``hour``         (int 0–23)
              - ``activity``     (str, from ``Activity`` enum values)

        Returns
        -------
        dict | None
            Prediction dict::

                {
                    "scene":      "focus_mode",
                    "confidence": 0.82,
                    "reason":     "You activate focus mode at this time on weekdays 82% of the time",
                    "entity_id":  "scene.focus_mode"
                }

            ``None`` if no pattern exceeds the confidence threshold.
        """
        day = int(context.get("day_of_week", datetime.now().weekday()))
        hour = int(context.get("hour", datetime.now().hour))

        hour_start = max(0, hour - _PATTERN_HOUR_WINDOW)
        hour_end = min(23, hour + _PATTERN_HOUR_WINDOW)

        best_scene: str | None = None
        best_confidence: float = 0.0
        best_reason: str = ""

        for scene_name in _SCENE_ENTITY_MAP:
            entity_id = f"{_SCENE_ENTITY_PREFIX}{scene_name}"

            try:
                patterns = self._pattern_engine.get_patterns(
                    entity_id=entity_id,
                    day_of_week=day,
                    time_range=(hour_start, hour_end),
                )
            except Exception as exc:
                log.warning(
                    "PatternEngine.get_patterns failed for %s: %s", entity_id, exc
                )
                continue

            if not patterns:
                continue

            # avg_value from the pattern engine is the rolling average of the
            # numeric state.  For scenes, 1.0 = on (activated), 0.0 = not.
            # confidence is already computed by the engine.  We combine both:
            # effective_confidence = avg_value × confidence (the pattern is
            # only meaningful when the state is consistently "on").
            for pattern in patterns:
                effective = pattern.avg_value * pattern.confidence
                if effective > best_confidence:
                    best_confidence = effective
                    best_scene = scene_name
                    day_label = _day_label(day)
                    pct = int(round(effective * 100))
                    best_reason = (
                        f"You activate {scene_name.replace('_', ' ')} "
                        f"around this time on {day_label} {pct}% of the time"
                    )

        if best_scene is None or best_confidence < self._confidence_threshold:
            log.debug(
                "No prediction above threshold %.2f (best=%.2f for %s).",
                self._confidence_threshold,
                best_confidence,
                best_scene,
            )
            return None

        log.info(
            "Prediction: scene=%s  confidence=%.2f  person=%s",
            best_scene,
            best_confidence,
            person,
        )

        return {
            "scene": best_scene,
            "confidence": best_confidence,
            "reason": best_reason,
            "entity_id": _SCENE_ENTITY_MAP[best_scene],
        }

    def should_activate(self, prediction: dict[str, Any]) -> bool:
        """
        Gate function: evaluate whether a prediction should actually be acted on.

        Checks:
        1. Confidence is above the configured threshold.
        2. The predicted scene is not already active.
        3. No *other* explicit scene is currently active (don't override a choice).
        4. The scene has not been rejected recently (rejection cache).

        Parameters
        ----------
        prediction:
            Dict as returned by ``predict_next_scene``.

        Returns
        -------
        bool
            ``True`` if the prediction should proceed to ``activate_prediction``.
        """
        scene = prediction.get("scene", "")
        confidence = float(prediction.get("confidence", 0.0))

        # 1. Confidence gate
        if confidence < self._confidence_threshold:
            log.debug(
                "should_activate: confidence %.2f < threshold %.2f — skip.",
                confidence,
                self._confidence_threshold,
            )
            return False

        # 2. Scene already active
        if self._is_scene_active(scene):
            log.debug("should_activate: scene '%s' is already active — skip.", scene)
            return False

        # 3. Another explicit scene is active
        if self._any_other_scene_active(scene):
            log.debug(
                "should_activate: a different scene is active — skip to avoid override."
            )
            return False

        # 4. Rejection cache
        if self._is_rejected(scene):
            log.debug(
                "should_activate: scene '%s' is in rejection cooldown — skip.", scene
            )
            return False

        return True

    def activate_prediction(
        self, prediction: dict[str, Any], person: str
    ) -> str:
        """
        Activate the predicted scene and return the announcement text.

        The announcement is deliberately understated — the room sets itself up;
        AURA does not trumpet its prediction algorithm.

        Parameters
        ----------
        prediction:
            Dict as returned by ``predict_next_scene``.
        person:
            Resident ID — used for personalised announcements and feedback
            attribution.

        Returns
        -------
        str
            Announcement text suitable for TTS.
        """
        scene = prediction.get("scene", "")
        entity_id = prediction.get("entity_id", "")
        confidence = float(prediction.get("confidence", 0.0))
        reason = prediction.get("reason", "")

        if not scene or not entity_id:
            log.warning("activate_prediction called with incomplete prediction: %s", prediction)
            return ""

        log.info(
            "Activating predicted scene: %s  (confidence=%.2f, person=%s)",
            scene,
            confidence,
            person,
        )

        self._ha_activate_scene(entity_id)
        self._record_scene_event(scene, person)

        announcement = _SCENE_ANNOUNCEMENTS.get(
            scene, f"{scene.replace('_', ' ').capitalize()} is set up."
        )

        # Register the prediction as in-flight so we can track feedback
        self._active_prediction = _Prediction(
            scene=scene,
            confidence=confidence,
            reason=reason,
            person=person,
        )

        log.debug(
            "Prediction %s registered — will resolve in %d–%ds.",
            self._active_prediction.prediction_id,
            self._rejection_window,
            self._acceptance_window,
        )

        return announcement

    def record_feedback(self, prediction_id: str, accepted: bool) -> None:
        """
        Record explicit feedback for a prediction and feed it back to the
        PatternEngine to adjust future fitness scores.

        Called by the voice agent when:
        - User says "that was a good call" / similar → ``accepted=True``
        - User overrides the scene within the rejection window → ``accepted=False``
        - The scene stays active past the acceptance window → ``accepted=True``
          (via ``_maybe_resolve_pending``)

        Parameters
        ----------
        prediction_id:
            ID returned by the ``_Prediction`` object, exposed via the active
            prediction's ``prediction_id`` attribute.  If the ID does not match
            the current in-flight prediction the call is a no-op.
        accepted:
            ``True`` for positive feedback, ``False`` for rejection.
        """
        if (
            self._active_prediction is None
            or self._active_prediction.prediction_id != prediction_id
        ):
            log.debug(
                "record_feedback: prediction_id %s does not match active prediction — ignoring.",
                prediction_id,
            )
            return

        pred = self._active_prediction
        self._active_prediction = None
        pred.resolved = True

        scene = pred.scene
        entity_id = f"{_SCENE_ENTITY_PREFIX}{scene}"

        if accepted:
            log.info("Prediction %s accepted — reinforcing pattern for %s.", prediction_id, scene)
            try:
                self._pattern_engine.record_event(
                    event_type=_SCENE_EVENT_TYPE,
                    entity_id=entity_id,
                    old_state="off",
                    new_state="on",
                    triggered_by="deja_vu_accepted",
                    person=pred.person,
                )
            except Exception as exc:
                log.warning("Failed to record acceptance to PatternEngine: %s", exc)
        else:
            log.info(
                "Prediction %s rejected — suppressing %s for %ds.",
                prediction_id,
                scene,
                self._rejection_suppress,
            )
            self._rejection_cache[scene] = time.monotonic()
            try:
                self._pattern_engine.record_event(
                    event_type="deja_vu_rejected",
                    entity_id=entity_id,
                    old_state="on",
                    new_state="off",
                    triggered_by="deja_vu_rejected",
                    person=pred.person,
                )
            except Exception as exc:
                log.warning("Failed to record rejection to PatternEngine: %s", exc)

    def handle_voice_feedback(
        self, text: str, person: str
    ) -> str | None:
        """
        Process a natural-language feedback phrase from the voice agent.

        Recognises positive feedback phrases ("good call", "nice one", "that
        was right", "good prediction") and negative phrases ("wrong",
        "not that", "cancel that", "bad call").

        Parameters
        ----------
        text:
            Transcribed phrase from the user (lowercased before matching).
        person:
            Resident ID — passed through to ``record_feedback``.

        Returns
        -------
        str | None
            Acknowledgement text suitable for TTS, or ``None`` if no
            active prediction or no feedback phrase was detected.
        """
        if self._active_prediction is None:
            return None

        lower = text.lower()

        positive_phrases = {
            "good call", "nice one", "good prediction", "that was right",
            "perfect", "exactly", "nailed it", "that was a good prediction",
            "smart", "you knew", "you read my mind",
        }
        negative_phrases = {
            "wrong", "not that", "bad call", "cancel that", "stop", "undo",
            "no", "bad prediction", "didn't ask for that", "change it back",
        }

        if any(phrase in lower for phrase in positive_phrases):
            pred_id = self._active_prediction.prediction_id
            self.record_feedback(pred_id, accepted=True)
            return "Good to know. I'll remember that."

        if any(phrase in lower for phrase in negative_phrases):
            pred_id = self._active_prediction.prediction_id
            self.record_feedback(pred_id, accepted=False)
            return "Got it. I'll dial that back."

        return None

    # ------------------------------------------------------------------
    # Internal — state checks
    # ------------------------------------------------------------------

    def _is_scene_active(self, scene_name: str) -> bool:
        """
        Return True if the input_boolean for the given scene is currently on.
        Returns False when HA is unreachable (fail open — still attempt activation).
        """
        boolean_id = _SCENE_BOOLEAN_MAP.get(scene_name)
        if not boolean_id:
            return False
        return self._ha_boolean_is_on(boolean_id)

    def _any_other_scene_active(self, exclude_scene: str) -> bool:
        """
        Return True if any scene *other than* ``exclude_scene`` has its
        tracking boolean set to on.
        """
        for scene_name, boolean_id in _SCENE_BOOLEAN_MAP.items():
            if scene_name == exclude_scene:
                continue
            if self._ha_boolean_is_on(boolean_id):
                log.debug(
                    "_any_other_scene_active: '%s' is on (excluding '%s').",
                    scene_name,
                    exclude_scene,
                )
                return True
        return False

    def _is_rejected(self, scene_name: str) -> bool:
        """
        Return True if the scene is in the rejection cooldown window.
        Expired entries are pruned lazily on access.
        """
        ts = self._rejection_cache.get(scene_name)
        if ts is None:
            return False
        elapsed = time.monotonic() - ts
        if elapsed > self._rejection_suppress:
            del self._rejection_cache[scene_name]
            return False
        return True

    def _maybe_resolve_pending(self) -> None:
        """
        Resolve the active prediction automatically based on elapsed time.

        - Past the acceptance window with no override → record as accepted.
        - Should not be called while still in the rejection window (the voice
          agent's override detection handles that window).
        """
        if self._active_prediction is None:
            return

        pred = self._active_prediction
        if pred.resolved:
            self._active_prediction = None
            return

        age = pred.age_seconds
        if age >= self._acceptance_window:
            log.debug(
                "Prediction %s auto-accepted after %.0fs (window=%ds).",
                pred.prediction_id,
                age,
                self._acceptance_window,
            )
            self.record_feedback(pred.prediction_id, accepted=True)

    # ------------------------------------------------------------------
    # Internal — Home Assistant calls
    # ------------------------------------------------------------------

    def _ha_boolean_is_on(self, entity_id: str) -> bool:
        """
        Query a single HA input_boolean state.
        Returns False on any network/auth error.
        """
        url = f"{self._ha_url}/api/states/{entity_id}"
        try:
            resp = requests.get(url, headers=self._ha_headers, timeout=4)
            if resp.status_code == 200:
                return resp.json().get("state") == "on"
        except requests.RequestException as exc:
            log.debug("HA state query failed for %s: %s", entity_id, exc)
        return False

    def _ha_activate_scene(self, entity_id: str) -> None:
        """
        Call ``scene.turn_on`` for the given scene entity.
        Errors are logged and swallowed — the announcement still goes out.
        """
        url = f"{self._ha_url}/api/services/scene/turn_on"
        payload = {"entity_id": entity_id}
        try:
            resp = requests.post(
                url, headers=self._ha_headers, json=payload, timeout=5
            )
            if resp.status_code in (200, 201):
                log.debug("scene.turn_on for %s succeeded.", entity_id)
            else:
                log.warning(
                    "scene.turn_on for %s returned HTTP %d.",
                    entity_id,
                    resp.status_code,
                )
        except requests.exceptions.ConnectionError:
            log.error("Cannot reach HA to activate scene %s.", entity_id)
        except requests.exceptions.Timeout:
            log.error("Timeout activating scene %s.", entity_id)
        except Exception as exc:
            log.error("Unexpected error activating %s: %s", entity_id, exc)

    def _record_scene_event(self, scene_name: str, person: str) -> None:
        """
        Record the Deja Vu-triggered scene activation to the PatternEngine so
        it contributes to future pattern confidence.
        """
        entity_id = f"{_SCENE_ENTITY_PREFIX}{scene_name}"
        try:
            self._pattern_engine.record_event(
                event_type=_SCENE_EVENT_TYPE,
                entity_id=entity_id,
                old_state="off",
                new_state="on",
                triggered_by="deja_vu",
                person=person,
            )
        except Exception as exc:
            log.warning(
                "Failed to record deja_vu scene event to PatternEngine: %s", exc
            )

    # ------------------------------------------------------------------
    # Internal — context helpers
    # ------------------------------------------------------------------

    def _build_context(
        self, context: dict[str, Any] | None
    ) -> dict[str, Any]:
        """
        Fill in missing context keys from the current system clock.
        """
        now = datetime.now(timezone.utc)
        base: dict[str, Any] = {
            "day_of_week": now.weekday(),
            "hour": now.hour,
            "activity": "unknown",
        }
        if context:
            base.update(context)
        return base

    # ------------------------------------------------------------------
    # Properties (read-only)
    # ------------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        """Whether Deja Vu predictive activation is currently enabled."""
        return self._enabled

    @property
    def active_prediction(self) -> _Prediction | None:
        """The current in-flight prediction, or None."""
        return self._active_prediction

    @property
    def confidence_threshold(self) -> float:
        """Minimum confidence required to activate a prediction."""
        return self._confidence_threshold


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _day_label(day_of_week: int) -> str:
    """Return a natural-language day label from a 0-indexed weekday int."""
    labels = [
        "Mondays", "Tuesdays", "Wednesdays", "Thursdays",
        "Fridays", "Saturdays", "Sundays",
    ]
    if 0 <= day_of_week <= 6:
        return labels[day_of_week]
    return "this day"
