"""
AURA Voice Agent — Health Endpoint
====================================
Provides a lightweight health status report for the webhook dispatcher's
/health route, callable from the desktop health_check.sh script.

Usage inside webhook_dispatcher.py::

    from health import health_response

    # Register a GET handler — or adapt do_GET to call this directly.
    dispatcher.register_get("health", lambda _: health_response())

Or, if you wire it into WebhookHandler.do_GET directly::

    if self.path.strip("/") == "health":
        body = health_response().encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return

No third-party dependencies. All imports are stdlib or already present in
the voice-agent package.
"""

from __future__ import annotations

import importlib.util
import json
import os
import socket
import time
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Version — bump this when the voice agent has a meaningful release.
# ---------------------------------------------------------------------------
VERSION = "0.5.0"

# ---------------------------------------------------------------------------
# Module-load time — used as the origin point for uptime_seconds.
# ---------------------------------------------------------------------------
_BOOT_TIME: float = time.monotonic()

# Resolve paths relative to this file so health checks work whether the
# process is started from /config/aura or any other working directory.
_VOICE_AGENT_DIR = Path(__file__).resolve().parent


def _check_module_importable(module_name: str) -> str:
    """Return 'ok' if the named module can be found, 'error' otherwise."""
    spec = importlib.util.find_spec(module_name)
    return "ok" if spec is not None else "error"


def _check_yaml_exists(filename: str) -> str:
    """Return 'ok' if the YAML file exists in the voice-agent directory."""
    return "ok" if (_VOICE_AGENT_DIR / filename).exists() else "error"


def _check_env_var(var_name: str) -> str:
    """Return 'ok' if the environment variable is set and non-empty."""
    value = os.environ.get(var_name, "")
    return "ok" if value else "error"


def _get_guest_mode_state() -> str:
    """
    Return the current guest mode state without importing the full
    GuestMode class (avoids pulling in side-effects at health-check time).

    Reads the persisted JSON state file directly. Falls back to 'unknown'
    if the file is absent or unreadable — that is not a failure condition.
    """
    candidate_paths = [
        Path("/config/aura/data/guest_mode.json"),
        _VOICE_AGENT_DIR.parent / "memory" / "guest_mode.json",
    ]
    for path in candidate_paths:
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return "active" if data.get("active", False) else "inactive"
            except (OSError, json.JSONDecodeError):
                return "unknown"
    return "inactive"  # no state file = guest mode has never been activated


def _check_voice_pipeline() -> str:
    """
    Verify the core voice-pipeline modules are importable.
    Returns 'ok' if all required modules are present, 'degraded' if
    optional modules are missing, 'error' if required modules are missing.
    """
    required = ["faster_whisper", "pyaudio", "anthropic", "elevenlabs"]
    optional = ["openwakeword", "numpy"]

    missing_required = [m for m in required if _check_module_importable(m) == "error"]
    missing_optional = [m for m in optional if _check_module_importable(m) == "error"]

    if missing_required:
        return "error"
    if missing_optional:
        return "degraded"
    return "ok"


def _check_learning() -> str:
    """
    Return 'ok' if the learning package is importable, 'degraded' if the
    package directory exists but lacks an __init__.py, 'error' if absent.
    """
    learning_dir = _VOICE_AGENT_DIR.parent / "learning"
    if not learning_dir.exists():
        return "error"
    init_file = learning_dir / "__init__.py"
    if not init_file.exists():
        return "degraded"
    spec = importlib.util.find_spec("learning")
    return "ok" if spec is not None else "degraded"


def get_health_status() -> dict:
    """
    Build and return a health status dictionary.

    Structure
    ---------
    {
        "status":          "ok" | "degraded" | "error",
        "version":         str,
        "hostname":        str,
        "timestamp":       str (ISO 8601, UTC),
        "uptime_seconds":  float,
        "components": {
            "voice_pipeline": "ok" | "degraded" | "error",
            "personality":    "ok" | "error",
            "config":         "ok" | "error",
            "env":            "ok" | "degraded" | "error",
            "learning":       "ok" | "degraded" | "error",
            "guest_mode":     "active" | "inactive" | "unknown"
        }
    }

    Overall status rules
    --------------------
    - "error"    : any component is "error"
    - "degraded" : no errors but at least one component is "degraded"
    - "ok"       : all components are "ok", "inactive", or "active"
    """
    # --- individual component checks ---
    voice_pipeline = _check_voice_pipeline()
    personality    = _check_yaml_exists("personality.yaml")
    config         = _check_yaml_exists("config.yaml")

    # Both keys must be present and non-empty for env to be "ok".
    # If only one is missing it's "degraded"; both missing is "error".
    anthropic_ok   = _check_env_var("ANTHROPIC_API_KEY")
    elevenlabs_ok  = _check_env_var("ELEVENLABS_API_KEY")
    if anthropic_ok == "ok" and elevenlabs_ok == "ok":
        env_status = "ok"
    elif anthropic_ok == "error" and elevenlabs_ok == "error":
        env_status = "error"
    else:
        env_status = "degraded"

    learning   = _check_learning()
    guest_mode = _get_guest_mode_state()

    components: dict[str, str] = {
        "voice_pipeline": voice_pipeline,
        "personality":    personality,
        "config":         config,
        "env":            env_status,
        "learning":       learning,
        "guest_mode":     guest_mode,
    }

    # --- roll up to overall status ---
    # guest_mode is informational — "active"/"inactive" are both healthy.
    status_values = [
        v for k, v in components.items() if k != "guest_mode"
    ]

    if "error" in status_values:
        overall = "error"
    elif "degraded" in status_values:
        overall = "degraded"
    else:
        overall = "ok"

    return {
        "status":         overall,
        "version":        VERSION,
        "hostname":       socket.gethostname(),
        "timestamp":      datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": round(time.monotonic() - _BOOT_TIME, 2),
        "components":     components,
    }


def health_response() -> str:
    """
    Return a JSON string of the health status, suitable for writing
    directly to an HTTP response body.

    Example usage in WebhookHandler.do_GET::

        body = health_response().encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    """
    return json.dumps(get_health_status(), indent=2)
