"""
AURA Clap Detection Listener
============================
Listens continuously on a USB microphone for clap patterns and fires
Home Assistant webhooks when a pattern is recognised.

Supported patterns (configurable in config.yaml):
  - Double clap  → Welcome Home scene toggle
  - Triple clap  → Studio / Content Mode toggle
  - Quad clap    → Party Mode toggle

Run directly:
    python clap_listener.py

Or via systemd:
    systemctl start clap_service
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pyaudio
import requests
import yaml
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Logging — structured, timestamped, flushed immediately (PYTHONUNBUFFERED=1
# is set by the systemd unit, but we set stream=sys.stdout explicitly so
# journald captures every line in order).
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("aura.clap")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
CONFIG_PATH = SCRIPT_DIR / "config.yaml"
ENV_PATH = PROJECT_ROOT / ".env"


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def load_config() -> dict[str, Any]:
    """Load and return the YAML configuration from config.yaml."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config file not found: {CONFIG_PATH}")
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        config: dict[str, Any] = yaml.safe_load(fh)
    log.info("Loaded config from %s", CONFIG_PATH)
    return config


def resolve_ha_settings(config: dict[str, Any]) -> tuple[str, str]:
    """
    Return (ha_url, ha_token) from environment variables, falling back to the
    YAML config for the URL.  The token must come from the environment — it is
    never stored in config.yaml.
    """
    ha_url: str = os.getenv("HA_URL") or config["homeassistant"]["url"]
    ha_token: str = os.getenv("HA_TOKEN", "")
    if not ha_token:
        log.warning(
            "HA_TOKEN is not set.  Webhook calls will be unauthenticated.  "
            "Set HA_TOKEN in the project .env file."
        )
    return ha_url.rstrip("/"), ha_token


# ---------------------------------------------------------------------------
# Core detector
# ---------------------------------------------------------------------------

class ClapDetector:
    """
    Listens on the default audio input device for clap-like transients and
    matches them against configured patterns.

    Detection algorithm
    -------------------
    A "clap" is an audio chunk whose RMS amplitude exceeds `threshold`.  To
    avoid double-counting a single clap that spans multiple chunks, a
    `min_silence_before` guard ensures we only register a new clap after a
    period of quiet.  Pattern matching is time-windowed: successive claps are
    grouped if the gap between them is less than `pattern_timeout` seconds.
    Once the window expires (or the maximum pattern count is reached), the
    accumulated count is matched against the configured patterns, longest
    match wins, and the corresponding webhook is fired.

    Parameters
    ----------
    config:
        Parsed config.yaml dict.
    ha_url:
        Base URL of the Home Assistant instance.
    ha_token:
        Long-Lived Access Token for HA (may be empty string).
    """

    def __init__(
        self,
        config: dict[str, Any],
        ha_url: str,
        ha_token: str,
    ) -> None:
        audio_cfg = config["audio"]
        detection_cfg = config["detection"]
        patterns_cfg = config["patterns"]

        # Audio settings
        self._sample_rate: int = int(audio_cfg["sample_rate"])
        self._chunk_size: int = int(audio_cfg["chunk_size"])
        self._channels: int = int(audio_cfg["channels"])
        self._pa_format: int = pyaudio.paInt16  # always 16-bit

        # Detection tuning
        self._threshold: float = float(detection_cfg["threshold"])
        self._pattern_timeout: float = float(detection_cfg["pattern_timeout"])
        self._cooldown: float = float(detection_cfg["cooldown"])
        self._min_silence_before: float = float(detection_cfg["min_silence_before"])

        # Patterns — sort descending by count so longer patterns match first
        self._patterns: list[dict[str, Any]] = sorted(
            patterns_cfg.values(), key=lambda p: p["count"], reverse=True
        )
        self._max_pattern_count: int = max(p["count"] for p in self._patterns)

        # HA webhook config
        self._ha_url = ha_url
        self._headers: dict[str, str] = {}
        if ha_token:
            self._headers["Authorization"] = f"Bearer {ha_token}"

        # Runtime state
        self._pyaudio: pyaudio.PyAudio | None = None
        self._stream: pyaudio.Stream | None = None
        self._running: bool = False

        # Clap accumulation state
        self._clap_times: list[float] = []
        self._last_clap_time: float = 0.0
        self._last_trigger_time: float = 0.0
        self._in_clap: bool = False          # True while audio is above threshold
        self._silence_start: float = time.monotonic()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Open the audio stream and begin the detection loop."""
        log.info("AURA Clap Detector starting…")
        log.info(
            "Settings — threshold: %.0f  pattern_timeout: %.2fs  "
            "cooldown: %.2fs  min_silence_before: %.2fs",
            self._threshold,
            self._pattern_timeout,
            self._cooldown,
            self._min_silence_before,
        )
        self._log_patterns()

        self._pyaudio = pyaudio.PyAudio()
        self._open_stream()

        self._running = True
        log.info("Listening for claps…")
        self._detection_loop()

    def stop(self) -> None:
        """Signal the detection loop to exit and release audio resources."""
        log.info("Shutting down clap detector…")
        self._running = False
        self._close_stream()

    # ------------------------------------------------------------------
    # Audio stream management
    # ------------------------------------------------------------------

    def _open_stream(self) -> None:
        """Open the PyAudio input stream, retrying on transient failures."""
        assert self._pyaudio is not None
        while True:
            try:
                self._stream = self._pyaudio.open(
                    format=self._pa_format,
                    channels=self._channels,
                    rate=self._sample_rate,
                    input=True,
                    frames_per_buffer=self._chunk_size,
                )
                log.info(
                    "Audio stream opened (rate=%d Hz, chunk=%d samples)",
                    self._sample_rate,
                    self._chunk_size,
                )
                return
            except OSError as exc:
                log.error("Failed to open audio stream: %s — retrying in 5 s", exc)
                time.sleep(5)

    def _close_stream(self) -> None:
        """Safely close the PyAudio stream and terminate the PyAudio instance."""
        if self._stream is not None:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:  # noqa: BLE001 — best-effort cleanup
                pass
            self._stream = None
        if self._pyaudio is not None:
            try:
                self._pyaudio.terminate()
            except Exception:  # noqa: BLE001 — best-effort cleanup
                pass
            self._pyaudio = None

    # ------------------------------------------------------------------
    # Detection loop
    # ------------------------------------------------------------------

    def _detection_loop(self) -> None:
        """
        Main processing loop.  Reads audio chunks, computes RMS amplitude,
        and delegates to the clap state machine.
        """
        while self._running:
            try:
                raw = self._stream.read(  # type: ignore[union-attr]
                    self._chunk_size, exception_on_overflow=False
                )
            except OSError as exc:
                log.error("Audio read error: %s — attempting stream recovery…", exc)
                self._close_stream()
                if not self._running:
                    break
                self._pyaudio = pyaudio.PyAudio()
                self._open_stream()
                continue

            rms = self._compute_rms(raw)
            now = time.monotonic()

            self._update_state(rms, now)

            # Check whether the open pattern window has expired
            if self._clap_times and (now - self._clap_times[-1]) > self._pattern_timeout:
                self._evaluate_pattern(now)

    def _compute_rms(self, raw: bytes) -> float:
        """Return the RMS amplitude of a raw 16-bit PCM audio chunk."""
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        if samples.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(samples ** 2)))

    def _update_state(self, rms: float, now: float) -> None:
        """
        Drive the clap detection state machine for one audio chunk.

        States
        ------
        Idle → if RMS exceeds threshold and silence guard is satisfied,
               register a clap onset and transition to In-Clap.
        In-Clap → once RMS drops below threshold, record silence start
                  and return to Idle.
        """
        in_cooldown = (now - self._last_trigger_time) < self._cooldown
        if in_cooldown:
            return

        if rms >= self._threshold:
            if not self._in_clap:
                # Check silence guard — require a brief quiet before each clap
                silence_duration = now - self._silence_start
                if silence_duration >= self._min_silence_before:
                    self._register_clap(now)
            self._in_clap = True
        else:
            if self._in_clap:
                self._silence_start = now
            self._in_clap = False

    def _register_clap(self, now: float) -> None:
        """Record a clap timestamp and immediately evaluate if the max count is reached."""
        self._clap_times.append(now)
        self._last_clap_time = now
        count = len(self._clap_times)
        log.debug("Clap detected (count so far: %d)", count)

        if count >= self._max_pattern_count:
            self._evaluate_pattern(now)

    # ------------------------------------------------------------------
    # Pattern matching and webhook firing
    # ------------------------------------------------------------------

    def _evaluate_pattern(self, now: float) -> None:
        """
        Compare accumulated clap count against configured patterns and fire
        the matching webhook.  Clears state regardless of whether a match
        was found.
        """
        count = len(self._clap_times)
        self._clap_times = []

        if count < 2:
            # Single clap or noise — no action
            return

        matched = self._match_pattern(count)
        if matched:
            log.info(
                "Pattern matched: %d clap(s) → %s (%s)",
                count,
                matched["webhook_id"],
                matched["description"],
            )
            self._last_trigger_time = now
            self._fire_webhook(matched["webhook_id"])
        else:
            log.info("No pattern matched for %d clap(s) — ignoring.", count)

    def _match_pattern(self, count: int) -> dict[str, Any] | None:
        """
        Return the first pattern whose count equals `count`, or None.
        Patterns are pre-sorted descending so longer patterns take priority
        when counts overlap (unlikely with exact matching, but safe).
        """
        for pattern in self._patterns:
            if pattern["count"] == count:
                return pattern
        return None

    def _fire_webhook(self, webhook_id: str) -> None:
        """POST to the Home Assistant webhook endpoint for `webhook_id`."""
        url = f"{self._ha_url}/api/webhook/{webhook_id}"
        try:
            response = requests.post(
                url,
                headers=self._headers,
                timeout=5,
            )
            if response.status_code in (200, 201, 204):
                log.info("Webhook fired successfully: %s", webhook_id)
            else:
                log.warning(
                    "Webhook %s returned HTTP %d: %s",
                    webhook_id,
                    response.status_code,
                    response.text[:120],
                )
        except requests.exceptions.ConnectionError as exc:
            log.error("Connection error firing webhook %s: %s", webhook_id, exc)
        except requests.exceptions.Timeout:
            log.error("Timeout firing webhook %s (limit: 5 s)", webhook_id)
        except requests.exceptions.RequestException as exc:
            log.error("Unexpected error firing webhook %s: %s", webhook_id, exc)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _log_patterns(self) -> None:
        """Log the configured patterns at startup for operator visibility."""
        log.info("Configured patterns:")
        for pattern in sorted(self._patterns, key=lambda p: p["count"]):
            log.info(
                "  %d clap(s) → /%s  (%s)",
                pattern["count"],
                pattern["webhook_id"],
                pattern["description"],
            )


# ---------------------------------------------------------------------------
# Test mode
# ---------------------------------------------------------------------------

def test_mode(duration: int, device_index: int | None) -> None:
    """
    Record audio for `duration` seconds and print real-time RMS levels so the
    operator can calibrate the detection threshold without triggering webhooks.

    Prints one RMS reading every 0.1 s, then reports:
      - Ambient floor  : average RMS over the entire recording
      - Peak RMS       : highest single-chunk RMS observed
      - Recommended threshold: midpoint between floor and peak
    """
    sample_rate = 44100
    chunk_size = 1024
    channels = 1
    pa_format = pyaudio.paInt16

    pa = pyaudio.PyAudio()

    open_kwargs: dict[str, object] = dict(
        format=pa_format,
        channels=channels,
        rate=sample_rate,
        input=True,
        frames_per_buffer=chunk_size,
    )
    if device_index is not None:
        open_kwargs["input_device_index"] = device_index

    try:
        stream = pa.open(**open_kwargs)  # type: ignore[arg-type]
    except OSError as exc:
        print(f"ERROR: Could not open audio device: {exc}", file=sys.stderr)
        pa.terminate()
        sys.exit(1)

    print(f"Recording for {duration} second(s) — make some noise to calibrate...")
    print(f"{'Time':>6}  {'RMS':>8}")
    print("-" * 18)

    rms_values: list[float] = []
    # Each report interval covers ~0.1 s worth of chunks
    chunks_per_report = max(1, int(round(sample_rate * 0.1 / chunk_size)))
    end_time = time.monotonic() + duration

    chunk_buffer: list[float] = []

    while time.monotonic() < end_time:
        try:
            raw = stream.read(chunk_size, exception_on_overflow=False)
        except OSError as exc:
            print(f"WARNING: Audio read error: {exc}", file=sys.stderr)
            continue

        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        rms = float(np.sqrt(np.mean(samples ** 2))) if samples.size > 0 else 0.0
        rms_values.append(rms)
        chunk_buffer.append(rms)

        if len(chunk_buffer) >= chunks_per_report:
            report_rms = max(chunk_buffer)
            elapsed = duration - (end_time - time.monotonic())
            print(f"{elapsed:>6.1f}s  {report_rms:>8.1f}")
            chunk_buffer = []

    stream.stop_stream()
    stream.close()
    pa.terminate()

    if not rms_values:
        print("No audio data captured.", file=sys.stderr)
        sys.exit(1)

    floor = float(np.mean(rms_values))
    peak = float(np.max(rms_values))
    recommended = (floor + peak) / 2.0

    print()
    print("=== Calibration Results ===")
    print(f"  Ambient floor (avg RMS) : {floor:>8.1f}")
    print(f"  Peak RMS                : {peak:>8.1f}")
    print(f"  Recommended threshold   : {recommended:>8.1f}")
    print()
    print(f"Set `detection.threshold` in config.yaml to ~{recommended:.0f}")


# ---------------------------------------------------------------------------
# Signal handling
# ---------------------------------------------------------------------------

_detector_instance: ClapDetector | None = None


def _handle_signal(signum: int, _frame: Any) -> None:
    """Handle SIGINT / SIGTERM for a clean shutdown."""
    sig_name = signal.Signals(signum).name
    log.info("Received %s — initiating clean shutdown…", sig_name)
    if _detector_instance is not None:
        _detector_instance.stop()
    sys.exit(0)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Parse CLI arguments, then either run test mode or the normal daemon loop."""
    global _detector_instance  # noqa: PLW0603 — intentional module-level singleton

    parser = argparse.ArgumentParser(
        description="AURA Clap Detection Listener",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Enter calibration test mode: record audio and report RMS levels.",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=5,
        metavar="N",
        help="Duration in seconds for test mode recording.",
    )
    parser.add_argument(
        "--device",
        type=int,
        default=None,
        metavar="N",
        help="PyAudio device index to use (default: system default input).",
    )
    args = parser.parse_args()

    if args.test:
        test_mode(duration=args.duration, device_index=args.device)
        return

    # Normal daemon mode -------------------------------------------------------

    # Load .env from project root (silently ignored if absent on the Pi)
    load_dotenv(ENV_PATH)

    # Register signal handlers before any blocking work
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    config = load_config()
    ha_url, ha_token = resolve_ha_settings(config)

    _detector_instance = ClapDetector(config, ha_url, ha_token)

    try:
        _detector_instance.start()
    except Exception as exc:  # noqa: BLE001 — top-level catch-all to log before exit
        log.critical("Fatal error in clap detector: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
