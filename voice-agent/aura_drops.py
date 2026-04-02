"""
AURA Drops — Voice-Created Scene Snapshots
==========================================
Lets residents snapshot the current state of every controllable device with a
single voice command ("Hey Aura, save this as Vibe Check") and recall it later
("Hey Aura, activate Vibe Check").

Each snapshot — called a "Drop" — captures the full live state of every
controllable entity (lights, switches, climate, media_player, cover) at the
moment the command is issued.  Drops are stored in a SQLite database on the Pi
so they survive reboots and AURA updates.

Design decisions
----------------
- SQLite is the right tool here: zero external dependencies, transactional,
  reliable on the Pi's SD card, and trivially backupable.  The DB lives at
  ``/config/aura/data/drops.db`` on the Pi, inside the HA config volume which
  is already backed up by HA's built-in snapshot system.
- Entity state is stored as a JSON blob in ``entities_snapshot``.  This avoids
  schema migrations when new entity types are added — the snapshot format is
  self-describing.
- Restoration is domain-aware: each HA service domain has a different "restore"
  service (``light.turn_on`` vs ``switch.turn_on`` vs ``climate.set_temperature``
  etc.).  The ``_restore_entity`` method routes by domain.
- Transition timing: lights get a 0.3 s stagger during restore for a smooth
  cascade effect.  Non-light entities (switches, climate) are applied
  immediately since they don't benefit from visual staggering.
- Names are case-insensitive for lookup but stored with original case for
  display.  Duplicate names are rejected at save time with a clear error.
- A ``UNIQUE`` constraint on the ``name`` column (case-folded) is enforced at
  the SQLite level so concurrent saves never silently overwrite each other.

Database schema (``drops`` table)
----------------------------------
  id                INTEGER  PRIMARY KEY AUTOINCREMENT
  name              TEXT     UNIQUE NOT NULL           — display name (original case)
  name_lower        TEXT     UNIQUE NOT NULL           — lower-cased for lookups
  created_by        TEXT     NOT NULL                  — person key ("conaugh" / "adon")
  created_at        TEXT     NOT NULL                  — ISO-8601 UTC timestamp
  entities_snapshot TEXT     NOT NULL                  — JSON array of entity snapshots

Usage (standalone smoke-test)::

    HA_URL=http://homeassistant.local:8123 \
    HA_TOKEN=your_token \
    python aura_drops.py
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

log = logging.getLogger("aura.drops")

# Default database path on the Pi — inside the HA config volume.
_DEFAULT_DB_PATH = Path("/config/aura/data/drops.db")

# HA domains and their restore strategies.
# Each key is a domain; value is a dict describing how to restore it.
_RESTORE_MAP: dict[str, dict[str, Any]] = {
    "light": {
        "on_service": "turn_on",
        "off_service": "turn_off",
        "on_attrs": ["brightness", "rgb_color", "color_temp", "effect"],
    },
    "switch": {
        "on_service": "turn_on",
        "off_service": "turn_off",
        "on_attrs": [],
    },
    "input_boolean": {
        "on_service": "turn_on",
        "off_service": "turn_off",
        "on_attrs": [],
    },
    "fan": {
        "on_service": "turn_on",
        "off_service": "turn_off",
        "on_attrs": ["percentage", "preset_mode"],
    },
    "cover": {
        "on_service": "open_cover",
        "off_service": "close_cover",
        "on_attrs": [],
    },
    "media_player": {
        "on_service": "media_play",
        "off_service": "media_stop",
        "on_attrs": ["volume_level"],
    },
    "climate": {
        "on_service": "set_temperature",
        "off_service": "turn_off",
        "on_attrs": ["temperature", "hvac_mode", "target_temp_high", "target_temp_low"],
    },
}

# Domains for which staggered timing is applied during restore.
_STAGGER_DOMAINS: frozenset[str] = frozenset({"light"})

# Stagger delay (seconds) between light restorations.
_STAGGER_DELAY: float = 0.3

# HA controllable domains to snapshot.
_SNAPSHOT_DOMAINS: frozenset[str] = frozenset(_RESTORE_MAP.keys())

# HA REST API timeout (seconds).
_HA_TIMEOUT: int = 5


class AuraDrops:
    """
    Manages AURA Drops — named snapshots of the full apartment device state.

    Parameters
    ----------
    ha_url:
        Base URL of the Home Assistant instance, e.g.
        ``http://homeassistant.local:8123``.
    ha_token:
        Long-lived access token for the HA REST API.
    db_path:
        Path to the SQLite database file.  The parent directory is created
        if it does not exist.  Defaults to ``/config/aura/data/drops.db``.
    """

    def __init__(
        self,
        ha_url: str,
        ha_token: str,
        db_path: Path = _DEFAULT_DB_PATH,
    ) -> None:
        if not ha_token:
            log.warning("HA_TOKEN is empty — HA service calls will fail.")

        self._ha_url: str = ha_url.rstrip("/")
        self._ha_headers: dict[str, str] = {
            "Authorization": f"Bearer {ha_token}",
            "Content-Type": "application/json",
        }
        self._db_path: Path = Path(db_path)

        self._init_db()
        log.info("AuraDrops initialised — DB: %s", self._db_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_drop(self, name: str, person: str) -> str:
        """
        Snapshot the current apartment state and save it as a named Drop.

        Parameters
        ----------
        name:
            Display name for the Drop, e.g. ``"Vibe Check"``.  Must not be
            empty.  Duplicate names (case-insensitive) are rejected.
        person:
            Resident identifier who issued the save command (``"conaugh"`` /
            ``"adon"``).

        Returns
        -------
        str
            Confirmation message suitable for TTS, e.g.
            ``"Saved 'Vibe Check' — 8 devices captured."``.
            Returns an error message string on any failure.
        """
        name = name.strip()
        if not name:
            return "You need to give the drop a name. Like, 'save this as Chill Mode'."

        person = person.strip() or "unknown"
        name_lower = name.lower()

        # Prevent overwriting an existing drop silently.
        if self._drop_exists(name_lower):
            return (
                f"There's already a drop called '{name}'. "
                f"Delete it first if you want to replace it."
            )

        # Fetch current entity states.
        all_states = self._fetch_all_states()
        if not all_states:
            return "Couldn't reach Home Assistant right now. Try again in a second."

        # Filter to controllable domains and snapshot each entity.
        snapshots: list[dict[str, Any]] = []
        for state in all_states:
            entity_id: str = state.get("entity_id", "")
            domain = entity_id.split(".")[0] if "." in entity_id else ""
            if domain not in _SNAPSHOT_DOMAINS:
                continue
            snapshot = self._snapshot_entity(state)
            snapshots.append(snapshot)

        if not snapshots:
            return "No controllable devices found to snapshot."

        # Persist to SQLite.
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO drops
                        (name, name_lower, created_by, created_at, entities_snapshot)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (name, name_lower, person, now_iso, json.dumps(snapshots)),
                )
        except sqlite3.IntegrityError:
            # Race condition — another save with the same name beat us.
            return (
                f"There's already a drop called '{name}'. "
                f"Delete it first if you want to replace it."
            )
        except sqlite3.Error as exc:
            log.error("SQLite error saving drop %r: %s", name, exc, exc_info=True)
            return f"Couldn't save '{name}' — database error. Check the logs."

        device_count = len(snapshots)
        log.info(
            "Drop %r saved by %s — %d entities captured.", name, person, device_count
        )
        return (
            f"Saved '{name}' — "
            f"{device_count} device{'s' if device_count != 1 else ''} captured."
        )

    def activate_drop(self, name: str) -> str:
        """
        Restore a saved Drop by replaying its entity state to Home Assistant.

        Parameters
        ----------
        name:
            Name of the Drop to activate (case-insensitive).

        Returns
        -------
        str
            Confirmation or error message suitable for TTS.
        """
        name = name.strip()
        if not name:
            return "Which drop do you want to activate?"

        row = self._fetch_drop(name.lower())
        if row is None:
            return (
                f"I don't have a drop called '{name}'. "
                f"Say 'what drops do I have?' to see your saved ones."
            )

        display_name: str = row["name"]
        try:
            snapshots: list[dict[str, Any]] = json.loads(row["entities_snapshot"])
        except (json.JSONDecodeError, KeyError) as exc:
            log.error("Corrupt snapshot data for drop %r: %s", display_name, exc)
            return f"'{display_name}' has corrupt data and can't be restored."

        if not snapshots:
            return f"'{display_name}' has no devices saved in it."

        log.info("Activating drop %r — %d entities.", display_name, len(snapshots))

        # Separate lights (staggered) from everything else (immediate).
        light_snapshots = [s for s in snapshots if s.get("domain") == "light"]
        other_snapshots = [s for s in snapshots if s.get("domain") != "light"]

        # Apply non-light entities first — they set the functional state.
        for snapshot in other_snapshots:
            self._restore_entity(snapshot)

        # Apply lights with stagger for cinematic effect.
        for index, snapshot in enumerate(light_snapshots):
            self._restore_entity(snapshot)
            if index < len(light_snapshots) - 1:
                time.sleep(_STAGGER_DELAY)

        log.info("Drop %r activated successfully.", display_name)
        return f"Activating '{display_name}'..."

    def list_drops(self) -> list[dict[str, Any]]:
        """
        Return all saved Drops ordered by creation date (newest first).

        Returns
        -------
        list[dict[str, Any]]
            Each dict contains: ``name``, ``created_by``, ``created_at``,
            ``entity_count``.  Returns an empty list on any error.
        """
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    SELECT name, created_by, created_at, entities_snapshot
                    FROM drops
                    ORDER BY created_at DESC
                    """
                )
                rows = cursor.fetchall()
        except sqlite3.Error as exc:
            log.error("SQLite error listing drops: %s", exc, exc_info=True)
            return []

        result: list[dict[str, Any]] = []
        for row in rows:
            try:
                entities = json.loads(row["entities_snapshot"])
                entity_count = len(entities)
            except (json.JSONDecodeError, TypeError):
                entity_count = 0

            result.append(
                {
                    "name": row["name"],
                    "created_by": row["created_by"],
                    "created_at": row["created_at"],
                    "entity_count": entity_count,
                }
            )

        return result

    def list_drops_summary(self) -> str:
        """
        Return a TTS-friendly summary of all saved Drops.

        Returns
        -------
        str
            Plain-text summary, e.g.
            ``"You've got 3 drops: Vibe Check (8 devices), ..."``.
        """
        drops = self.list_drops()
        if not drops:
            return "You don't have any drops saved yet. Say 'save this as [name]' to create one."

        count = len(drops)
        names_with_counts = [
            f"{d['name']} ({d['entity_count']} device{'s' if d['entity_count'] != 1 else ''})"
            for d in drops
        ]

        if count == 1:
            return f"You've got one drop: {names_with_counts[0]}."

        names_str = ", ".join(names_with_counts[:-1]) + f", and {names_with_counts[-1]}"
        return f"You've got {count} drops: {names_str}."

    def delete_drop(self, name: str) -> str:
        """
        Delete a saved Drop by name (case-insensitive).

        Parameters
        ----------
        name:
            Name of the Drop to delete.

        Returns
        -------
        str
            Confirmation or error message suitable for TTS.
        """
        name = name.strip()
        if not name:
            return "Which drop do you want to delete?"

        name_lower = name.lower()

        # Fetch the actual display name so the confirmation uses original case.
        row = self._fetch_drop(name_lower)
        if row is None:
            return f"I don't have a drop called '{name}'."

        display_name: str = row["name"]

        try:
            with self._connect() as conn:
                conn.execute(
                    "DELETE FROM drops WHERE name_lower = ?", (name_lower,)
                )
        except sqlite3.Error as exc:
            log.error("SQLite error deleting drop %r: %s", display_name, exc, exc_info=True)
            return f"Couldn't delete '{display_name}' — database error."

        log.info("Drop %r deleted.", display_name)
        return f"Deleted '{display_name}'."

    # ------------------------------------------------------------------
    # Private helpers — snapshot and restore
    # ------------------------------------------------------------------

    def _snapshot_entity(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        Extract the restorable attributes from a raw HA entity state dict.

        Parameters
        ----------
        state:
            Raw entity state dict from ``/api/states``.

        Returns
        -------
        dict[str, Any]
            A compact snapshot containing ``entity_id``, ``domain``,
            ``state``, and the subset of attributes that can be replayed
            via HA services.

        Notes
        -----
        Only attributes listed in :data:`_RESTORE_MAP` for the entity's domain
        are captured.  Unknown attributes are ignored to keep snapshots lean and
        avoid replaying read-only or computed attributes.
        """
        entity_id: str = state.get("entity_id", "")
        domain = entity_id.split(".")[0] if "." in entity_id else ""
        current_state: str = state.get("state", "off")
        attrs: dict[str, Any] = state.get("attributes", {})

        # Determine which attributes to capture for this domain.
        domain_map = _RESTORE_MAP.get(domain, {})
        on_attrs: list[str] = domain_map.get("on_attrs", [])

        captured_attrs: dict[str, Any] = {}
        for attr in on_attrs:
            if attr in attrs and attrs[attr] is not None:
                captured_attrs[attr] = attrs[attr]

        return {
            "entity_id": entity_id,
            "domain": domain,
            "state": current_state,
            "attributes": captured_attrs,
        }

    def _restore_entity(self, snapshot: dict[str, Any]) -> None:
        """
        Replay a single entity snapshot to Home Assistant via the REST API.

        Routes to the correct HA service based on entity domain and the
        ``state`` value (``"on"`` / ``"playing"`` / ``"open"`` → on service;
        everything else → off service).

        Failures are logged and swallowed so a single unavailable device does
        not interrupt the rest of the restore.

        Parameters
        ----------
        snapshot:
            A single entity snapshot dict as produced by :meth:`_snapshot_entity`.
        """
        entity_id: str = snapshot.get("entity_id", "")
        domain: str = snapshot.get("domain", "")
        state: str = snapshot.get("state", "off")
        attrs: dict[str, Any] = snapshot.get("attributes", {})

        if not entity_id or not domain:
            log.warning("Skipping malformed snapshot: %s", snapshot)
            return

        domain_map = _RESTORE_MAP.get(domain)
        if domain_map is None:
            log.debug("No restore strategy for domain %r — skipping %s.", domain, entity_id)
            return

        # Determine which service to call based on the saved state.
        _ON_STATES = {"on", "playing", "open", "heat", "cool", "auto", "fan_only", "dry"}
        is_on = state.lower() in _ON_STATES

        if is_on:
            service = domain_map["on_service"]
            # Build service data from captured attributes.
            service_data: dict[str, Any] = {"entity_id": entity_id}
            for attr, value in attrs.items():
                if value is not None:
                    service_data[attr] = value
        else:
            service = domain_map["off_service"]
            service_data = {"entity_id": entity_id}

        # Special case: climate restore always needs hvac_mode even when "off".
        if domain == "climate" and not is_on:
            service = "set_hvac_mode"
            service_data["hvac_mode"] = "off"

        url = f"{self._ha_url}/api/services/{domain}/{service}"
        log.debug(
            "Restoring %s — %s.%s  data=%s", entity_id, domain, service, service_data
        )

        try:
            resp = requests.post(
                url,
                headers=self._ha_headers,
                json=service_data,
                timeout=_HA_TIMEOUT,
            )
            if resp.status_code in (200, 201):
                log.debug("Restored %s successfully.", entity_id)
            else:
                log.warning(
                    "Restore %s returned HTTP %d: %s",
                    entity_id,
                    resp.status_code,
                    resp.text[:120],
                )
        except requests.exceptions.ConnectionError:
            log.error("Cannot reach HA to restore %s.", entity_id)
        except requests.exceptions.Timeout:
            log.error("Timeout restoring %s.", entity_id)
        except Exception as exc:  # noqa: BLE001
            log.error("Unexpected error restoring %s: %s", entity_id, exc)

    # ------------------------------------------------------------------
    # Private helpers — HA integration
    # ------------------------------------------------------------------

    def _fetch_all_states(self) -> list[dict[str, Any]]:
        """
        Fetch all entity states from ``/api/states``.

        Returns an empty list on any network or auth failure so the caller can
        handle the missing-data case explicitly.
        """
        url = f"{self._ha_url}/api/states"
        try:
            resp = requests.get(url, headers=self._ha_headers, timeout=_HA_TIMEOUT)
            resp.raise_for_status()
            return resp.json()  # type: ignore[no-any-return]
        except requests.exceptions.ConnectionError:
            log.warning("Cannot reach Home Assistant at %s.", self._ha_url)
        except requests.exceptions.Timeout:
            log.warning("HA /api/states request timed out.")
        except requests.exceptions.HTTPError as exc:
            log.warning("HA /api/states returned HTTP %s.", exc.response.status_code)
        except Exception as exc:  # noqa: BLE001
            log.warning("Unexpected error fetching HA states: %s", exc)
        return []

    # ------------------------------------------------------------------
    # Private helpers — SQLite
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        """
        Create the database directory and the ``drops`` table if they do not
        already exist.

        Raises
        ------
        RuntimeError
            If the database cannot be initialised (disk full, permission denied,
            etc.).  Propagated to the caller so startup fails loudly rather than
            silently storing no data.
        """
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise RuntimeError(
                f"Cannot create AuraDrops DB directory {self._db_path.parent}: {exc}"
            ) from exc

        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS drops (
                        id                INTEGER PRIMARY KEY AUTOINCREMENT,
                        name              TEXT    NOT NULL,
                        name_lower        TEXT    NOT NULL UNIQUE,
                        created_by        TEXT    NOT NULL,
                        created_at        TEXT    NOT NULL,
                        entities_snapshot TEXT    NOT NULL
                    )
                    """
                )
            log.debug("Drops table ensured at %s.", self._db_path)
        except sqlite3.Error as exc:
            raise RuntimeError(
                f"Failed to initialise AuraDrops database at {self._db_path}: {exc}"
            ) from exc

    def _connect(self) -> sqlite3.Connection:
        """
        Open a SQLite connection with row_factory set for dict-style access.

        Returns
        -------
        sqlite3.Connection
            An open connection configured for use as a context manager.
        """
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _drop_exists(self, name_lower: str) -> bool:
        """Return True if a Drop with the given lower-cased name already exists."""
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    "SELECT 1 FROM drops WHERE name_lower = ? LIMIT 1",
                    (name_lower,),
                )
                return cursor.fetchone() is not None
        except sqlite3.Error as exc:
            log.warning("SQLite error checking drop existence: %s", exc)
            return False

    def _fetch_drop(self, name_lower: str) -> sqlite3.Row | None:
        """
        Fetch a single Drop row by lower-cased name.

        Returns
        -------
        sqlite3.Row | None
            The full row, or ``None`` if not found.
        """
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    "SELECT * FROM drops WHERE name_lower = ? LIMIT 1",
                    (name_lower,),
                )
                return cursor.fetchone()
        except sqlite3.Error as exc:
            log.error("SQLite error fetching drop %r: %s", name_lower, exc, exc_info=True)
            return None


# ---------------------------------------------------------------------------
# Standalone smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os
    import sys
    from pathlib import Path
    from dotenv import load_dotenv

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        stream=sys.stdout,
    )

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    ha_url = os.getenv("HA_URL", "http://homeassistant.local:8123")
    ha_token = os.getenv("HA_TOKEN", "")

    # Use a local test DB so the smoke test doesn't touch the Pi.
    test_db = Path("/tmp/aura_drops_test.db")

    drops = AuraDrops(ha_url=ha_url, ha_token=ha_token, db_path=test_db)

    print("\n--- Saving a drop ---")
    print(drops.save_drop("Test Vibe", "conaugh"))

    print("\n--- Listing drops ---")
    print(drops.list_drops_summary())

    print("\n--- Activating drop ---")
    print(drops.activate_drop("Test Vibe"))

    print("\n--- Deleting drop ---")
    print(drops.delete_drop("Test Vibe"))

    print("\n--- Listing after delete ---")
    print(drops.list_drops_summary())
