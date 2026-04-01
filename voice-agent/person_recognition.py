"""
AURA Person Recognition
=======================
Determines who is speaking or who just arrived home.

Two complementary strategies are provided:

Context-based (always available)
---------------------------------
If only one resident is home according to Home Assistant, any voice command
must be from them — no audio analysis needed.  ``identify_by_context()``
implements this fast path.

Voice signature (Phase 1 — lightweight)
-----------------------------------------
``identify_by_wake_word()`` accepts an ``audio_features`` dict produced by a
lightweight audio analyser (pitch + energy envelope) and compares it against
per-person voice profiles stored in the learning database config.  This is NOT
deep ML — it is just enough to distinguish two known voices without requiring
a full speaker-diarisation model.  Accuracy improves as profiles are refined.

Presence detection
-------------------
``get_home_status()``, ``who_just_arrived()``, and ``who_is_home()`` all query
the Home Assistant ``person.*`` entities via the REST API.  They mirror the
entity IDs defined in ``learning/config.yaml`` so configuration stays in one
place.

Usage::

    from person_recognition import PersonRecognizer

    recognizer = PersonRecognizer(ha_url=..., ha_token=..., config=...)

    # Fast path — who is home right now?
    home = recognizer.who_is_home()          # ["conaugh"]

    # Best guess from context alone
    person = recognizer.identify_by_context()  # "conaugh" | None

    # Who just walked in? (call after an HA state-change event)
    arrived = recognizer.who_just_arrived()   # "adon" | None
"""

from __future__ import annotations

import logging
from typing import Any

import requests

log = logging.getLogger("aura.person_recognition")

# HA states that mean a person entity is considered "home".
_HOME_STATES: frozenset[str] = frozenset({"home"})

# HA states that mean a person entity is considered "away".
_AWAY_STATES: frozenset[str] = frozenset({"not_home", "away"})

# Default voice signature comparison tolerance.
# A normalised Euclidean distance below this threshold is a "match".
_VOICE_MATCH_THRESHOLD = 0.25


class PersonRecognizer:
    """
    Identifies which resident is present or speaking.

    Parameters
    ----------
    ha_url:
        Base URL of the Home Assistant instance, e.g.
        ``http://homeassistant.local:8123``.
    ha_token:
        Long-lived access token for the HA REST API.  Can be an empty string —
        HA calls will fail gracefully if the token is absent.
    config:
        The full project config dict.  Reads the ``persons`` list from
        ``learning/config.yaml`` (merged into the top-level config by the
        caller if needed).  Expected shape::

            persons:
              - id: conaugh
                display_name: "Conaugh"
                phone_entity: "person.conaugh"
              - id: adon
                display_name: "Adon"
                phone_entity: "person.adon"

    Raises
    ------
    ValueError
        If ``config`` contains no ``persons`` entries.
    """

    def __init__(
        self,
        ha_url: str,
        ha_token: str,
        config: dict[str, Any],
    ) -> None:
        self._ha_url: str = ha_url.rstrip("/")
        self._ha_headers: dict[str, str] = {
            "Authorization": f"Bearer {ha_token}",
            "Content-Type": "application/json",
        }

        # Build the person registry from config.
        persons_cfg: list[dict[str, Any]] = config.get("persons", [])
        if not persons_cfg:
            raise ValueError(
                "No persons configured. "
                "Add at least one entry to the 'persons' list in learning/config.yaml."
            )

        # person_id → {display_name, phone_entity, voice_profile}
        self._persons: dict[str, dict[str, Any]] = {}
        for person in persons_cfg:
            person_id: str = person["id"].lower()
            self._persons[person_id] = {
                "display_name": person.get("display_name", person_id.capitalize()),
                "phone_entity": person.get("phone_entity", f"person.{person_id}"),
                # Voice profiles start empty; populated by update_voice_profile().
                "voice_profile": person.get("voice_profile", {}),
            }

        # Cache for the previous HA presence snapshot.
        # Used by who_just_arrived() to detect state transitions.
        self._previous_states: dict[str, str] = {}

        log.info(
            "PersonRecognizer initialised — tracking %d resident(s): %s",
            len(self._persons),
            ", ".join(self._persons.keys()),
        )

    # ------------------------------------------------------------------
    # Voice-based identification
    # ------------------------------------------------------------------

    def identify_by_context(self) -> str | None:
        """
        Identify who is speaking based purely on presence context.

        If exactly one resident is home, that resident is almost certainly the
        speaker — return their person ID.  If multiple residents are home, or
        if HA is unreachable, return ``None`` so the caller can fall back to
        voice-signature identification.

        Returns
        -------
        str | None
            Person ID (e.g. ``"conaugh"``) or ``None`` if ambiguous.
        """
        home = self.who_is_home()

        if len(home) == 1:
            log.debug("identify_by_context: single resident home → %s", home[0])
            return home[0]

        if len(home) == 0:
            log.debug(
                "identify_by_context: no residents home — voice from outside or HA unreachable."
            )
            return None

        log.debug(
            "identify_by_context: multiple residents home (%s) — cannot determine speaker.",
            home,
        )
        return None

    def identify_by_wake_word(
        self, audio_features: dict[str, float]
    ) -> str | None:
        """
        Identify a speaker from lightweight audio features.

        This method does NOT use deep ML.  It computes a simple normalised
        Euclidean distance between the provided features and each resident's
        stored voice profile.  It is designed to distinguish two known voices
        in a quiet apartment environment, not to handle arbitrary speakers.

        Parameters
        ----------
        audio_features:
            Dict of extracted audio features, e.g.::

                {
                    "pitch_mean_hz": 145.3,
                    "pitch_std_hz":  18.2,
                    "energy_mean":    0.042,
                    "energy_std":     0.011,
                    "spectral_centroid": 2100.0,
                }

        Returns
        -------
        str | None
            Person ID of the best match if confidence is above threshold,
            otherwise ``None``.

        Notes
        -----
        Voice profiles are populated by repeated calls to
        ``update_voice_profile()``.  If a profile is empty the person is
        skipped.  A minimum of ~10 samples is recommended before trusting
        results.

        The feature set can be extended without changing this method by
        updating the profile dicts — only keys present in BOTH the incoming
        features and the stored profile are compared.
        """
        if not audio_features:
            return None

        best_person: str | None = None
        best_distance: float = float("inf")

        for person_id, data in self._persons.items():
            profile: dict[str, float] = data.get("voice_profile", {})
            if not profile:
                log.debug(
                    "identify_by_wake_word: no voice profile for %s — skipping.",
                    person_id,
                )
                continue

            distance = self._feature_distance(audio_features, profile)
            log.debug(
                "Voice distance for %s: %.4f (threshold %.4f)",
                person_id,
                distance,
                _VOICE_MATCH_THRESHOLD,
            )

            if distance < best_distance:
                best_distance = distance
                best_person = person_id

        if best_person is not None and best_distance <= _VOICE_MATCH_THRESHOLD:
            log.info(
                "identify_by_wake_word: matched %s (distance=%.4f)",
                best_person,
                best_distance,
            )
            return best_person

        log.debug(
            "identify_by_wake_word: no confident match (best_distance=%.4f).",
            best_distance,
        )
        return None

    def update_voice_profile(
        self,
        person: str,
        audio_features: dict[str, float],
    ) -> None:
        """
        Update a resident's voice profile by averaging in new features.

        Uses an exponential moving average (alpha=0.2) so recent samples have
        more influence than older ones.

        Parameters
        ----------
        person:
            Resident ID (``"conaugh"`` / ``"adon"``).
        audio_features:
            New feature dict to incorporate into the profile.
        """
        person = person.lower()
        if person not in self._persons:
            log.warning(
                "update_voice_profile: unknown person %r — ignoring.", person
            )
            return

        alpha = 0.2  # EMA weight for new samples
        profile: dict[str, float] = self._persons[person].get("voice_profile", {})

        updated: dict[str, float] = {}
        for key, value in audio_features.items():
            if key in profile:
                updated[key] = (1 - alpha) * profile[key] + alpha * value
            else:
                updated[key] = value  # First sample — accept as-is

        self._persons[person]["voice_profile"] = updated
        log.debug("Voice profile updated for %s: %s", person, updated)

    # ------------------------------------------------------------------
    # Presence detection
    # ------------------------------------------------------------------

    def get_home_status(self) -> dict[str, str]:
        """
        Query HA for the current state of all person entities.

        Returns
        -------
        dict[str, str]
            Mapping of person ID → raw HA state string, e.g.
            ``{"conaugh": "home", "adon": "not_home"}``.
            Returns an empty dict if HA is unreachable.
        """
        result: dict[str, str] = {}

        for person_id, data in self._persons.items():
            entity_id: str = data["phone_entity"]
            state = self._fetch_entity_state(entity_id)
            if state is not None:
                result[person_id] = state

        log.debug("Home status: %s", result)
        return result

    def who_is_home(self) -> list[str]:
        """
        Return a list of resident IDs currently at home.

        Uses the ``person.*`` entity states from Home Assistant.  Returns an
        empty list if HA is unreachable.

        Returns
        -------
        list[str]
            Person IDs of everyone currently home, e.g. ``["conaugh"]``.
        """
        status = self.get_home_status()
        home = [pid for pid, state in status.items() if state in _HOME_STATES]
        log.debug("who_is_home: %s", home)
        return home

    def who_just_arrived(self) -> str | None:
        """
        Detect which resident transitioned to 'home' since the last poll.

        Compares the current HA presence snapshot with the internally cached
        previous snapshot.  Updates the cache on every call.

        This method is designed to be called periodically (e.g. every 30 s by
        a background thread) — the first call always returns ``None`` because
        there is no previous state to compare against.

        Returns
        -------
        str | None
            Person ID of the resident who just arrived, or ``None`` if nobody
            transitioned to 'home' since the last poll.

        Notes
        -----
        If multiple residents arrive simultaneously (edge case), only the first
        one found is returned.  The caller's polling loop will catch the second
        on the next iteration.
        """
        current_states = self.get_home_status()

        just_arrived: str | None = None

        if self._previous_states:
            for person_id, current_state in current_states.items():
                previous_state = self._previous_states.get(person_id, "")
                was_away = previous_state in _AWAY_STATES or previous_state == ""
                is_home_now = current_state in _HOME_STATES
                if was_away and is_home_now:
                    log.info(
                        "%s just arrived home (was: %r, now: %r)",
                        person_id,
                        previous_state,
                        current_state,
                    )
                    just_arrived = person_id
                    break  # Surface one arrival at a time

        self._previous_states = current_states
        return just_arrived

    def get_display_name(self, person_id: str) -> str:
        """
        Return the display name for a person ID.

        Parameters
        ----------
        person_id:
            Resident key, e.g. ``"conaugh"``.

        Returns
        -------
        str
            Display name, e.g. ``"Conaugh"``.  Returns the capitalised person
            ID if not found in config.
        """
        data = self._persons.get(person_id.lower(), {})
        return data.get("display_name", person_id.capitalize())

    def get_person_ids(self) -> list[str]:
        """Return a list of all configured person IDs."""
        return list(self._persons.keys())

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _fetch_entity_state(self, entity_id: str) -> str | None:
        """
        Fetch the current state string for a single HA entity.

        Returns ``None`` on any network or auth failure so callers always
        receive a safe value.
        """
        url = f"{self._ha_url}/api/states/{entity_id}"
        try:
            resp = requests.get(url, headers=self._ha_headers, timeout=5)
            if resp.status_code == 404:
                log.warning(
                    "HA entity %r not found — check phone_entity in learning/config.yaml.",
                    entity_id,
                )
                return None
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return str(data.get("state", "unknown"))
        except requests.exceptions.ConnectionError:
            log.warning(
                "Cannot reach Home Assistant at %s — presence unknown.", self._ha_url
            )
            return None
        except requests.exceptions.Timeout:
            log.warning("Timeout fetching state for %r.", entity_id)
            return None
        except requests.exceptions.HTTPError as exc:
            log.warning(
                "HTTP %d fetching state for %r.",
                exc.response.status_code,
                entity_id,
            )
            return None
        except Exception as exc:  # noqa: BLE001
            log.warning("Unexpected error fetching state for %r: %s", entity_id, exc)
            return None

    @staticmethod
    def _feature_distance(
        a: dict[str, float],
        b: dict[str, float],
    ) -> float:
        """
        Compute a normalised Euclidean distance between two feature dicts.

        Only keys present in BOTH dicts are compared.  Each dimension is
        normalised by the stored profile value to make the metric
        scale-independent across features with very different magnitudes (e.g.
        pitch in Hz vs. energy near zero).

        Returns ``float('inf')`` if there are no overlapping keys.
        """
        common_keys = set(a.keys()) & set(b.keys())
        if not common_keys:
            return float("inf")

        total_sq = 0.0
        for key in common_keys:
            ref = b[key]
            if ref == 0.0:
                # Avoid division by zero — treat the dimension as zero distance
                # if the reference is zero and the incoming value is also zero.
                total_sq += 0.0 if a[key] == 0.0 else 1.0
            else:
                total_sq += ((a[key] - ref) / ref) ** 2

        return (total_sq / len(common_keys)) ** 0.5
