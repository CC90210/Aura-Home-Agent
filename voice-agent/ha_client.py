"""
Shared Home Assistant REST API client for all AURA voice-agent modules.

Every module that needs to talk to HA should accept an HAClient instance
instead of raw ha_url + ha_token strings. This eliminates ~500 lines of
duplicated HTTP boilerplate and ensures consistent error handling, timeouts,
and logging across the entire voice pipeline.

Usage:
    client = HAClient(ha_url, ha_token)
    state = client.get_state("light.living_room_leds")
    client.call_service("light", "turn_on", "light.living_room_leds", brightness_pct=80)

Thread safety:
    HAClient is safe to share across threads. ``requests.Session`` is not
    thread-safe by default, but the lock around every session call serialises
    concurrent access without measurable overhead at AURA's request volume.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger("aura.ha_client")

# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------
# Only retry on connection-level failures and 502/503/504 gateway errors.
# Never retry 401 (bad token) or 404 (missing entity) — those need fixing,
# not retrying. Total wall-clock overhead is at most ~2 s before giving up.
_RETRY_POLICY = Retry(
    total=2,
    backoff_factor=0.5,
    status_forcelist=(502, 503, 504),
    allowed_methods={"GET", "POST"},
    raise_on_status=False,
)

# ---------------------------------------------------------------------------
# Success status codes returned by the HA REST API
# ---------------------------------------------------------------------------
_OK_STATUSES: frozenset[int] = frozenset({200, 201})


class HAClient:
    """
    Thin, stateless wrapper around the Home Assistant REST API.

    All network errors are caught, logged, and converted to safe sentinel
    values (``None`` / ``False`` / ``[]``).  No call ever raises an exception
    to the caller — AURA modules should degrade gracefully when HA is offline.

    Parameters
    ----------
    base_url:
        Full URL to the HA instance, e.g. ``"http://homeassistant.local:8123"``.
        A trailing slash is stripped automatically.
    token:
        Long-Lived Access Token from HA → Profile → Long-Lived Access Tokens.
    timeout:
        Request timeout in seconds applied to every API call.  Defaults to
        8 s, which matches the longest timeout observed across existing modules.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: float = 8.0,
    ) -> None:
        if not base_url:
            raise ValueError("HAClient: base_url must not be empty.")
        if not token:
            raise ValueError(
                "HAClient: token must not be empty. "
                "Create a Long-Lived Access Token in HA > Profile > Long-Lived Access Tokens."
            )

        self._base_url: str = base_url.rstrip("/")
        self._timeout: float = timeout
        self._lock: threading.Lock = threading.Lock()

        # One session per client — keeps a TCP connection alive between calls
        # which matters when Ghost DJ / VibeSync poll HA every 60 seconds.
        self._session: requests.Session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
        )
        adapter = HTTPAdapter(max_retries=_RETRY_POLICY)
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)

        log.debug("HAClient ready — base_url=%s  timeout=%.1fs", self._base_url, timeout)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_state(self, entity_id: str) -> dict[str, Any] | None:
        """
        Fetch the full state object for a single entity.

        Returns the raw HA state dict on success::

            {
                "entity_id": "light.living_room_leds",
                "state": "on",
                "attributes": {"brightness": 128, "rgb_color": [255, 180, 100]},
                "last_changed": "2026-04-03T09:00:00+00:00",
                ...
            }

        Returns ``None`` if the entity does not exist (HTTP 404), if HA is
        unreachable, or on any other error.

        Parameters
        ----------
        entity_id:
            HA entity ID, e.g. ``"light.living_room_leds"``.
        """
        url = f"{self._base_url}/api/states/{entity_id}"
        try:
            resp = self._get(url)
        except _HAClientError as exc:
            log.warning("get_state(%s): %s", entity_id, exc)
            return None

        if resp.status_code == 404:
            log.debug("get_state(%s): entity not found in HA.", entity_id)
            return None

        if resp.status_code not in _OK_STATUSES:
            log.warning(
                "get_state(%s): unexpected HTTP %d.", entity_id, resp.status_code
            )
            return None

        data: dict[str, Any] = resp.json()
        return data

    def get_states(self) -> list[dict[str, Any]]:
        """
        Fetch all entity states from the HA instance.

        Returns a (potentially large) list of state dicts — one per entity
        registered in HA.  Returns an empty list on any failure so callers
        can treat a missing result as "no entities available" without crashing.
        """
        url = f"{self._base_url}/api/states"
        try:
            resp = self._get(url)
        except _HAClientError as exc:
            log.warning("get_states(): %s", exc)
            return []

        if resp.status_code not in _OK_STATUSES:
            log.warning("get_states(): unexpected HTTP %d.", resp.status_code)
            return []

        states: list[dict[str, Any]] = resp.json()
        return states

    def call_service(
        self,
        domain: str,
        service: str,
        entity_id: str | None = None,
        **data: Any,
    ) -> bool:
        """
        Call an HA service via ``POST /api/services/{domain}/{service}``.

        Parameters
        ----------
        domain:
            HA domain, e.g. ``"light"``, ``"media_player"``, ``"script"``.
        service:
            Service name, e.g. ``"turn_on"``, ``"play_media"``.
        entity_id:
            Target entity ID.  Pass ``None`` to omit the ``entity_id`` field
            entirely (some services, such as ``homeassistant.check_config``,
            do not accept one).
        **data:
            Additional service data fields merged into the request payload,
            e.g. ``brightness_pct=80``, ``rgb_color=[255, 100, 0]``.

        Returns
        -------
        bool
            ``True`` on HTTP 200/201, ``False`` on any failure.
        """
        url = f"{self._base_url}/api/services/{domain}/{service}"
        payload: dict[str, Any] = {}
        if entity_id is not None:
            payload["entity_id"] = entity_id
        payload.update(data)

        log.debug(
            "call_service(%s.%s) entity=%s data=%s",
            domain,
            service,
            entity_id,
            data or None,
        )

        try:
            resp = self._post(url, payload)
        except _HAClientError as exc:
            log.warning("call_service(%s.%s): %s", domain, service, exc)
            return False

        if resp.status_code in _OK_STATUSES:
            log.debug("call_service(%s.%s): OK", domain, service)
            return True

        log.warning(
            "call_service(%s.%s): HTTP %d — %s",
            domain,
            service,
            resp.status_code,
            resp.text[:120],
        )
        return False

    def fire_event(
        self,
        event_type: str,
        event_data: dict[str, Any] | None = None,
    ) -> bool:
        """
        Fire a custom HA event via ``POST /api/events/{event_type}``.

        Useful for triggering automations that listen for custom event types
        rather than webhook triggers.

        Parameters
        ----------
        event_type:
            The event type string, e.g. ``"aura_context_change"``.
        event_data:
            Optional dict of additional event data merged into the payload.

        Returns
        -------
        bool
            ``True`` on HTTP 200/201, ``False`` on any failure.
        """
        url = f"{self._base_url}/api/events/{event_type}"
        payload: dict[str, Any] = event_data or {}

        log.debug("fire_event(%s) data=%s", event_type, payload or None)

        try:
            resp = self._post(url, payload)
        except _HAClientError as exc:
            log.warning("fire_event(%s): %s", event_type, exc)
            return False

        if resp.status_code in _OK_STATUSES:
            log.debug("fire_event(%s): OK", event_type)
            return True

        log.warning(
            "fire_event(%s): HTTP %d — %s",
            event_type,
            resp.status_code,
            resp.text[:120],
        )
        return False

    def is_state(self, entity_id: str, state: str) -> bool:
        """
        Return ``True`` if ``entity_id`` is currently in ``state``.

        Case-insensitive comparison.  Returns ``False`` if the entity does not
        exist or HA is unreachable — the safe default for guards like
        "is silent mode on?" or "is music playing?".

        Parameters
        ----------
        entity_id:
            HA entity ID, e.g. ``"input_boolean.silent_mode"``.
        state:
            Expected state string, e.g. ``"on"``, ``"playing"``, ``"home"``.
        """
        result = self.get_state(entity_id)
        if result is None:
            return False
        current: str = result.get("state", "")
        return current.lower() == state.lower()

    def get_attribute(
        self,
        entity_id: str,
        attribute: str,
        default: Any = None,
    ) -> Any:
        """
        Return a single attribute value from an entity's state object.

        Parameters
        ----------
        entity_id:
            HA entity ID.
        attribute:
            Attribute key, e.g. ``"media_title"``, ``"brightness"``,
            ``"rgb_color"``.
        default:
            Value returned when the entity is missing, HA is unreachable, or
            the attribute key does not exist.  Defaults to ``None``.
        """
        result = self.get_state(entity_id)
        if result is None:
            return default
        return result.get("attributes", {}).get(attribute, default)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def base_url(self) -> str:
        """The base URL used for all API requests."""
        return self._base_url

    @property
    def timeout(self) -> float:
        """Per-request timeout in seconds."""
        return self._timeout

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"HAClient(base_url={self._base_url!r}, timeout={self._timeout}s)"

    # ------------------------------------------------------------------
    # Private — locked HTTP helpers
    # ------------------------------------------------------------------

    def _get(self, url: str) -> requests.Response:
        """
        Issue a GET request inside the thread lock.

        Raises ``_HAClientError`` on ``ConnectionError``, ``Timeout``, and
        any other ``RequestException`` so callers have a single exception type
        to handle.
        """
        try:
            with self._lock:
                return self._session.get(url, timeout=self._timeout)
        except requests.exceptions.ConnectionError as exc:
            raise _HAClientError(f"Cannot reach HA at {self._base_url}: {exc}") from exc
        except requests.exceptions.Timeout as exc:
            raise _HAClientError(f"Request timed out after {self._timeout}s: {url}") from exc
        except requests.exceptions.RequestException as exc:
            raise _HAClientError(f"Request failed: {exc}") from exc

    def _post(self, url: str, payload: dict[str, Any]) -> requests.Response:
        """
        Issue a POST request inside the thread lock.

        Raises ``_HAClientError`` on any network or transport failure.
        """
        try:
            with self._lock:
                return self._session.post(url, json=payload, timeout=self._timeout)
        except requests.exceptions.ConnectionError as exc:
            raise _HAClientError(f"Cannot reach HA at {self._base_url}: {exc}") from exc
        except requests.exceptions.Timeout as exc:
            raise _HAClientError(f"Request timed out after {self._timeout}s: {url}") from exc
        except requests.exceptions.RequestException as exc:
            raise _HAClientError(f"Request failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Internal exception — never escapes the public surface
# ---------------------------------------------------------------------------

class _HAClientError(Exception):
    """
    Internal transport error raised by ``_get`` / ``_post`` and immediately
    caught in every public method.  Never exposed to callers of HAClient.
    """
