"""
AURA Voice Agent — Main Daemon
===============================
Orchestrates the full voice pipeline:

  1. WakeWordDetector.listen()   — block until "Hey Aura" is detected
  2. Play listening chime        — short sine-wave tone via PyAudio
  3. SpeechRecorder.record()     — capture speech until silence (max 10 s)
  4. Play processing tone        — lower confirmation tone
  5. Transcriber.transcribe()    — convert audio to text via Whisper
  6. IntentHandler.process()     — send to Claude + execute HA actions
  7. TTSEngine.speak()           — play spoken response via ElevenLabs
  8. Repeat from step 1

Run as a long-running daemon:
    python aura_voice.py

Run one cycle and exit (for CI / manual testing):
    python aura_voice.py --test

The daemon handles SIGINT and SIGTERM for a clean shutdown — all audio
resources are released before the process exits.

Environment variables (loaded from project root .env):
    ELEVENLABS_API_KEY    — ElevenLabs API key
    ELEVENLABS_VOICE_ID   — ElevenLabs voice ID
    ANTHROPIC_API_KEY     — Anthropic API key
    HA_URL                — Home Assistant base URL (optional override)
    HA_TOKEN              — Home Assistant long-lived access token
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import signal
import struct
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pyaudio
import yaml
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths — all resolved relative to this file so the daemon can be started
# from any working directory (including via systemd).
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
CONFIG_PATH = SCRIPT_DIR / "config.yaml"
ENV_PATH = PROJECT_ROOT / ".env"

# ---------------------------------------------------------------------------
# Learning-module path setup — the learning package lives one level up.
# PROJECT_ROOT must be defined before this block.  sys.path is mutated so
# that both `person_recognition` (voice-agent/) and `learning` (project root)
# resolve correctly when the daemon starts from any working directory.
# ---------------------------------------------------------------------------
sys.path.insert(0, str(PROJECT_ROOT))

from person_recognition import PersonRecognizer  # noqa: E402 — after path setup

try:
    from learning.pattern_engine import ContextAwareness  # noqa: E402
    from learning.habit_tracker import HabitTracker  # noqa: E402
    _LEARNING_AVAILABLE = True
except ImportError:
    _LEARNING_AVAILABLE = False

# ---------------------------------------------------------------------------
# Logging — same format as clap_listener.py for consistency across services.
# PYTHONUNBUFFERED=1 is set in the systemd unit, but we stream to stdout
# explicitly so journald captures every line.
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("aura.voice")


# ---------------------------------------------------------------------------
# Configuration loader
# ---------------------------------------------------------------------------


def load_config() -> dict[str, Any]:
    """Load and return the YAML configuration from config.yaml."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config file not found: {CONFIG_PATH}")
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        config: dict[str, Any] = yaml.safe_load(fh)
    log.info("Loaded config from %s", CONFIG_PATH)
    return config


def resolve_secrets(config: dict[str, Any]) -> dict[str, str]:
    """
    Pull all required secrets from environment variables.

    Returns a dict with keys:
      - ha_url
      - ha_token
      - anthropic_api_key
      - elevenlabs_api_key
      - elevenlabs_voice_id

    Logs warnings for any missing optional values; raises ValueError if
    a required secret is absent.
    """
    ha_url: str = os.getenv("HA_URL") or config["homeassistant"]["url"]
    ha_token: str = os.getenv("HA_TOKEN", "")
    anthropic_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    elevenlabs_key: str = os.getenv("ELEVENLABS_API_KEY", "")
    elevenlabs_voice: str = os.getenv("ELEVENLABS_VOICE_ID", "")

    if not ha_token:
        log.warning("HA_TOKEN is not set — Home Assistant commands will fail.")
    if not anthropic_key:
        raise ValueError(
            "ANTHROPIC_API_KEY is required but not set.  "
            "Add it to the project .env file."
        )
    if not elevenlabs_key:
        log.warning(
            "ELEVENLABS_API_KEY is not set — AURA will not speak responses."
        )
    if not elevenlabs_voice:
        log.warning(
            "ELEVENLABS_VOICE_ID is not set — AURA will not speak responses."
        )

    return {
        "ha_url": ha_url.rstrip("/"),
        "ha_token": ha_token,
        "anthropic_api_key": anthropic_key,
        "elevenlabs_api_key": elevenlabs_key,
        "elevenlabs_voice_id": elevenlabs_voice,
    }


# ---------------------------------------------------------------------------
# Chime / tone generator
# ---------------------------------------------------------------------------


def _play_tone(
    frequency: float,
    duration: float,
    amplitude: float = 0.4,
    sample_rate: int = 16000,
    output_device: int | None = None,
) -> None:
    """
    Generate and immediately play a sine-wave tone using PyAudio.

    No audio file is needed — the waveform is computed with numpy.

    Parameters
    ----------
    frequency:
        Tone pitch in Hz (e.g. 880 for a high A).
    duration:
        Duration in seconds.
    amplitude:
        Peak amplitude in [0.0, 1.0].  0.4 is unobtrusive but audible.
    sample_rate:
        Samples per second.
    output_device:
        PyAudio output device index, or None for the system default.
    """
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)

    # Apply a short fade-in and fade-out (10 ms each) to avoid clicks
    fade_samples = min(int(sample_rate * 0.01), len(t))
    envelope = np.ones(len(t), dtype=np.float32)
    envelope[:fade_samples] = np.linspace(0.0, 1.0, fade_samples)
    envelope[-fade_samples:] = np.linspace(1.0, 0.0, fade_samples)

    wave = (np.sin(2 * math.pi * frequency * t) * amplitude * envelope).astype(np.float32)
    raw_bytes = struct.pack(f"{len(wave)}f", *wave)

    pa = pyaudio.PyAudio()
    try:
        stream = pa.open(
            format=pyaudio.paFloat32,
            channels=1,
            rate=sample_rate,
            output=True,
            output_device_index=output_device,
        )
        stream.write(raw_bytes)
        stream.stop_stream()
        stream.close()
    except OSError as exc:
        log.warning("Could not play tone (%.0f Hz): %s", frequency, exc)
    finally:
        pa.terminate()


def play_listening_chime(config: dict[str, Any]) -> None:
    """
    Play the two-note "AURA is listening" chime.

    Two ascending notes (C5 → E5) give a friendly "ding-ding" feel that is
    distinct from any alert tones and clearly signals readiness.
    """
    output_device: int | None = config.get("tts", {}).get("output_device")
    sample_rate: int = config["audio"]["sample_rate"]
    try:
        _play_tone(523.25, 0.12, sample_rate=sample_rate, output_device=output_device)  # C5
        time.sleep(0.04)
        _play_tone(659.25, 0.18, sample_rate=sample_rate, output_device=output_device)  # E5
    except Exception as exc:  # noqa: BLE001 — chime failure must not abort the pipeline
        log.warning("Listening chime failed: %s", exc)


def play_processing_tone(config: dict[str, Any]) -> None:
    """
    Play a single low tone to signal that AURA has finished recording and
    is now thinking.
    """
    output_device: int | None = config.get("tts", {}).get("output_device")
    sample_rate: int = config["audio"]["sample_rate"]
    try:
        _play_tone(
            392.0,
            0.15,
            amplitude=0.25,
            sample_rate=sample_rate,
            output_device=output_device,
        )  # G4 — subtle, lower-energy cue
    except Exception as exc:  # noqa: BLE001
        log.warning("Processing tone failed: %s", exc)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


class AuraVoiceAgent:
    """
    Top-level orchestrator.  Owns the component instances and the main loop.

    Parameters
    ----------
    config:
        Parsed config.yaml dict.
    secrets:
        Dict returned by ``resolve_secrets()``.
    test_mode:
        If True, run exactly one pipeline cycle then set ``_running = False``.
    """

    def __init__(
        self,
        config: dict[str, Any],
        secrets: dict[str, str],
        test_mode: bool = False,
    ) -> None:
        self._config = config
        self._secrets = secrets
        self._test_mode = test_mode
        self._running = False

        # Lazy-initialise components so imports surface clearly at startup
        self._detector: Any = None
        self._recorder: Any = None
        self._transcriber: Any = None
        self._tts: Any = None
        self._intent: Any = None

        # Learning / personality components — optional, degrade gracefully if
        # the learning package is not installed or its config is missing.
        self._recognizer: PersonRecognizer | None = None
        self._context: ContextAwareness | None = None  # type: ignore[assignment]
        self._habit_tracker: HabitTracker | None = None  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Initialise all components and enter the main loop."""
        log.info("AURA Voice Agent starting up…")
        self._init_components()
        self._running = True
        log.info("AURA is ready.  Listening for 'Hey Aura'…")
        self._main_loop()

    def stop(self) -> None:
        """Signal the main loop to exit on the next iteration."""
        log.info("AURA Voice Agent shutting down…")
        self._running = False
        if self._detector is not None:
            try:
                self._detector.close()
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------
    # Component initialisation
    # ------------------------------------------------------------------

    def _init_components(self) -> None:
        """Import and construct all pipeline components."""
        from wake_word import WakeWordDetector
        from stt import SpeechRecorder, Transcriber
        from tts import TTSEngine
        from intent_handler import IntentHandler

        log.info("Initialising wake word detector…")
        self._detector = WakeWordDetector(self._config)

        log.info("Initialising speech recorder…")
        self._recorder = SpeechRecorder(self._config)

        log.info("Initialising Whisper transcriber…")
        self._transcriber = Transcriber(self._config)

        if self._secrets["elevenlabs_api_key"] and self._secrets["elevenlabs_voice_id"]:
            log.info("Initialising ElevenLabs TTS engine…")
            self._tts = TTSEngine(
                api_key=self._secrets["elevenlabs_api_key"],
                voice_id=self._secrets["elevenlabs_voice_id"],
                config=self._config,
            )
        else:
            log.warning(
                "TTS engine disabled — ELEVENLABS_API_KEY or ELEVENLABS_VOICE_ID not set."
            )
            self._tts = None

        log.info("Initialising intent handler…")
        self._intent = IntentHandler(
            ha_url=self._secrets["ha_url"],
            ha_token=self._secrets["ha_token"],
            anthropic_api_key=self._secrets["anthropic_api_key"],
            config=self._config,
        )

        log.info("All components initialised.")

        # ── Optional learning / personality layer ───────────────────────
        learning_cfg_path = PROJECT_ROOT / "learning" / "config.yaml"

        try:
            self._recognizer = PersonRecognizer(
                ha_url=self._secrets["ha_url"],
                ha_token=self._secrets["ha_token"],
                config=self._config,
            )
            log.info("PersonRecognizer initialised.")
        except Exception as exc:  # noqa: BLE001
            log.warning("PersonRecognizer unavailable — person identification disabled: %s", exc)
            self._recognizer = None

        if _LEARNING_AVAILABLE:
            try:
                self._context = ContextAwareness(config_path=learning_cfg_path)
                log.info("ContextAwareness initialised.")
            except Exception as exc:  # noqa: BLE001
                log.warning("ContextAwareness unavailable — context detection disabled: %s", exc)
                self._context = None

            try:
                self._habit_tracker = HabitTracker(config_path=learning_cfg_path)
                log.info("HabitTracker initialised.")
            except Exception as exc:  # noqa: BLE001
                log.warning("HabitTracker unavailable — habit data disabled: %s", exc)
                self._habit_tracker = None
        else:
            log.warning(
                "Learning package not found — ContextAwareness and HabitTracker disabled."
            )

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _main_loop(self) -> None:
        """
        Run the voice pipeline in a loop until ``_running`` is False.

        Each iteration:
          1. Listen for wake word
          2. Play listening chime
          3. Record command
          4. Play processing tone
          5. Transcribe
          6. Process intent + execute HA actions
          7. Speak response
        """
        while self._running:
            try:
                self._run_one_cycle()
            except KeyboardInterrupt:
                log.info("KeyboardInterrupt in main loop — exiting.")
                self._running = False
                break
            except Exception as exc:  # noqa: BLE001 — top-level guard, never crash
                log.error(
                    "Unhandled error in voice pipeline — recovering: %s",
                    exc,
                    exc_info=True,
                )
                # Brief pause before retrying so we don't spin on a hard error
                time.sleep(2)

            if self._test_mode:
                log.info("Test mode — single cycle complete, exiting.")
                self._running = False

    def _run_one_cycle(self) -> None:
        """Execute one complete listen → respond cycle."""

        # ── Step 1: Wait for wake word ──────────────────────────────────
        log.debug("Waiting for wake word…")
        assert self._detector is not None
        self._detector.listen()

        # ── Step 2: Listening chime ─────────────────────────────────────
        play_listening_chime(self._config)
        log.info("Wake word confirmed — recording command…")

        # ── Step 3: Record command ──────────────────────────────────────
        assert self._recorder is not None
        audio = self._recorder.record()

        if audio is None or len(audio) == 0:
            log.warning("No audio captured — returning to wake word detection.")
            return

        # ── Step 4: Processing tone ─────────────────────────────────────
        play_processing_tone(self._config)

        # ── Step 5: Transcribe ──────────────────────────────────────────
        assert self._transcriber is not None
        user_text = self._transcriber.transcribe(audio)

        if not user_text:
            log.info("Transcription was empty — skipping intent processing.")
            self._speak("I didn't catch that. Please try again after the chime.")
            return

        log.info("Transcribed command: %r", user_text)

        # ── Step 6: Process intent + execute HA actions ─────────────────
        assert self._intent is not None

        # Identify who is speaking
        person: str | None = None
        context: str = "casual"
        habit_data: dict[str, Any] | None = None

        if self._recognizer:
            person = self._recognizer.identify_by_context()

        if self._context:
            ctx = self._context.get_current_context()
            context = ctx.activity.value if ctx.activity else "casual"

        if self._habit_tracker and person:
            try:
                report = self._habit_tracker.get_weekly_report(person)
                habit_data = {"streaks": report.streaks} if report else None
            except Exception:  # noqa: BLE001
                pass

        response_text = self._intent.process(
            user_text,
            person=person,
            context=context,
            habit_data=habit_data,
        )

        # Log the interaction for pattern learning
        if self._recognizer and person:
            if hasattr(self._recognizer, "_personality"):
                self._recognizer._personality.log_speech_pattern(person, user_text)  # noqa: SLF001

        self._log_event(user_text, person)

        # ── Step 7: Speak response ──────────────────────────────────────
        self._speak(response_text)

    def _speak(self, text: str) -> None:
        """Speak ``text`` if TTS is available; otherwise log the response."""
        if self._tts is not None:
            self._tts.speak(text)
        else:
            log.info("[TTS disabled] Response: %r", text)

    def _log_event(self, user_text: str, person: str | None) -> None:
        """
        Record this voice interaction in the pattern engine so the learning
        system has a complete picture of when and how voice commands are used.

        Silently skips if the learning package is unavailable or the engine
        raises — voice interaction must never fail because of logging.
        """
        if not _LEARNING_AVAILABLE or self._context is None:
            return

        try:
            self._context._engine.record_event(  # noqa: SLF001
                event_type="voice_command",
                entity_id="voice_agent.input",
                old_state=None,
                new_state=user_text[:255],  # guard against very long utterances
                triggered_by="user",
                person=person or "unknown",
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to log voice event to pattern engine: %s", exc)


# ---------------------------------------------------------------------------
# Signal handling
# ---------------------------------------------------------------------------

_agent_instance: AuraVoiceAgent | None = None


def _handle_signal(signum: int, _frame: Any) -> None:
    """Handle SIGINT / SIGTERM by requesting a clean shutdown."""
    sig_name = signal.Signals(signum).name
    log.info("Received %s — initiating clean shutdown…", sig_name)
    if _agent_instance is not None:
        _agent_instance.stop()
    sys.exit(0)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AURA Voice Agent — ambient AI for your apartment."
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run a single pipeline cycle and exit (useful for smoke-testing).",
    )
    return parser.parse_args()


def main() -> None:
    """
    Load configuration and secrets, construct the agent, and run the
    main loop.  Intended as the daemon entry point (called by systemd).
    """
    global _agent_instance  # noqa: PLW0603 — intentional module-level singleton

    args = _parse_args()

    # Load .env from project root before reading any env vars
    load_dotenv(ENV_PATH)

    # Register signal handlers before anything blocks
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        config = load_config()
        secrets = resolve_secrets(config)
    except (FileNotFoundError, ValueError) as exc:
        log.critical("Startup failed: %s", exc)
        sys.exit(1)

    _agent_instance = AuraVoiceAgent(config, secrets, test_mode=args.test)

    try:
        _agent_instance.start()
    except Exception as exc:  # noqa: BLE001 — fatal error, log before exit
        log.critical("Fatal error in AURA Voice Agent: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
