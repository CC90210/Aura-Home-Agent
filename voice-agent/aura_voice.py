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
sys.path.insert(0, str(SCRIPT_DIR))

from person_recognition import PersonRecognizer  # noqa: E402 — after path setup

try:
    from learning.pattern_engine import ContextAwareness  # noqa: E402
    from learning.habit_tracker import HabitTracker  # noqa: E402
    _LEARNING_AVAILABLE = True
except ImportError:
    _LEARNING_AVAILABLE = False

# Feature modules — all optional, graceful degradation if any are missing
# or if their dependencies (anthropic, requests) are not installed yet.
try:
    from mirror_mode import MirrorMode
    from aura_drops import AuraDrops
    from pulse_check import PulseCheck
    from ghost_dj import GhostDJ
    from vibe_sync import VibeSync
    from deja_vu import DejaVu
    from content_radar import ContentRadar
    from social_sonar import SocialSonar
    from phantom_presence import PhantomPresence
    from energy_oracle import EnergyOracle
    _FEATURES_AVAILABLE = True
except ImportError as _features_import_error:
    _FEATURES_AVAILABLE = False
    # Logged after the logging config is set up (see bottom of this block).
    _features_import_error_msg = str(_features_import_error)

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

if not _FEATURES_AVAILABLE:
    log.warning("Feature modules not fully available — some features disabled: %s", _features_import_error_msg)  # type: ignore[name-defined]


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
    raw_bytes = wave.tobytes()

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

        # Feature module instances — each is None until _init_components() runs.
        # Any feature that fails to initialise stays None; all callers guard with
        # `if self._<feature>:` before invoking, so one broken feature cannot
        # kill the rest of the pipeline.
        self._mirror_mode: Any = None
        self._drops: Any = None
        self._pulse_check: Any = None
        self._ghost_dj: Any = None
        self._vibe_sync: Any = None
        self._deja_vu: Any = None
        self._content_radar: Any = None
        self._social_sonar: Any = None
        self._phantom_presence: Any = None
        self._energy_oracle: Any = None
        self._dispatcher: Any = None

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

        # ── Feature modules ──────────────────────────────────────────────
        # Each feature is initialised independently so one failure cannot
        # prevent others from starting.  All failures are warnings, not errors.
        self._init_features()

        # ── Intent handler (needs features dict) ─────────────────────────
        # Built after features so we can pass the live instances in.
        log.info("Initialising intent handler…")
        features: dict[str, Any] = {}
        if self._mirror_mode:
            features["mirror_mode"] = self._mirror_mode
        if self._drops:
            features["aura_drops"] = self._drops
        if self._vibe_sync:
            features["vibe_sync"] = self._vibe_sync
        if self._deja_vu:
            features["deja_vu"] = self._deja_vu
        if self._pulse_check:
            features["pulse_check"] = self._pulse_check
        if self._ghost_dj:
            features["ghost_dj"] = self._ghost_dj
        if self._content_radar:
            features["content_radar"] = self._content_radar
        if self._energy_oracle:
            features["energy_oracle"] = self._energy_oracle

        self._intent = IntentHandler(
            ha_url=self._secrets["ha_url"],
            ha_token=self._secrets["ha_token"],
            anthropic_api_key=self._secrets["anthropic_api_key"],
            config=self._config,
            features=features,
        )

        log.info("All components initialised.")

        # ── Webhook dispatcher ───────────────────────────────────────────
        self._start_webhook_dispatcher()

    def _init_features(self) -> None:
        """
        Initialise all optional feature modules.

        Each feature is wrapped in its own try/except so a single broken
        feature (missing dependency, bad config, etc.) cannot prevent the
        others from starting.
        """
        if not _FEATURES_AVAILABLE:
            log.warning("Skipping feature initialisation — feature modules not available.")
            return

        ha_url: str = self._secrets["ha_url"]
        ha_token: str = self._secrets["ha_token"]
        api_key: str = self._secrets["anthropic_api_key"]

        try:
            self._mirror_mode = MirrorMode(ha_url, ha_token, api_key)
            log.info("MirrorMode initialised.")
        except Exception as exc:  # noqa: BLE001
            log.warning("MirrorMode init failed: %s", exc)

        try:
            drops_db = Path(PROJECT_ROOT) / "data" / "drops.db"
            self._drops = AuraDrops(ha_url, ha_token, drops_db)
            log.info("AuraDrops initialised.")
        except Exception as exc:  # noqa: BLE001
            log.warning("AuraDrops init failed: %s", exc)

        try:
            if self._habit_tracker is not None:
                personality = (
                    self._intent._personality  # noqa: SLF001
                    if self._intent and hasattr(self._intent, "_personality")
                    else None
                )
                if personality is not None:
                    self._pulse_check = PulseCheck(
                        ha_url, ha_token, self._habit_tracker, personality, api_key
                    )
                    log.info("PulseCheck initialised.")
                else:
                    log.warning("PulseCheck skipped — personality not yet loaded (intent handler not ready).")
        except Exception as exc:  # noqa: BLE001
            log.warning("PulseCheck init failed: %s", exc)

        try:
            if self._context is not None:
                self._ghost_dj = GhostDJ(
                    ha_url, ha_token,
                    context_awareness=self._context,
                    anthropic_api_key=api_key,
                )
                log.info("GhostDJ initialised.")
            else:
                self._ghost_dj = GhostDJ(ha_url, ha_token, anthropic_api_key=api_key)
                log.info("GhostDJ initialised (no context awareness).")
        except Exception as exc:  # noqa: BLE001
            log.warning("GhostDJ init failed: %s", exc)

        try:
            self._vibe_sync = VibeSync(ha_url, ha_token, anthropic_api_key=api_key)
            log.info("VibeSync initialised.")
        except Exception as exc:  # noqa: BLE001
            log.warning("VibeSync init failed: %s", exc)

        try:
            if self._context is not None and hasattr(self._context, "_engine"):
                self._deja_vu = DejaVu(
                    self._context._engine,  # noqa: SLF001
                    ha_url,
                    ha_token,
                )
                log.info("DejaVu initialised.")
        except Exception as exc:  # noqa: BLE001
            log.warning("DejaVu init failed: %s", exc)

        try:
            self._content_radar = ContentRadar(
                ha_url, ha_token,
                str(Path(PROJECT_ROOT) / "data" / "patterns.db"),
                api_key,
            )
            log.info("ContentRadar initialised.")
        except Exception as exc:  # noqa: BLE001
            log.warning("ContentRadar init failed: %s", exc)

        try:
            self._social_sonar = SocialSonar(ha_url, ha_token)
            log.info("SocialSonar initialised.")
        except Exception as exc:  # noqa: BLE001
            log.warning("SocialSonar init failed: %s", exc)

        try:
            if self._context is not None and hasattr(self._context, "_engine"):
                self._phantom_presence = PhantomPresence(self._context._engine)  # noqa: SLF001
                log.info("PhantomPresence initialised.")
        except Exception as exc:  # noqa: BLE001
            log.warning("PhantomPresence init failed: %s", exc)

        try:
            if (
                self._context is not None
                and hasattr(self._context, "_engine")
                and self._habit_tracker is not None
                and self._content_radar is not None
            ):
                self._energy_oracle = EnergyOracle(
                    ha_url,
                    ha_token,
                    api_key,
                    self._context._engine,  # noqa: SLF001
                    self._habit_tracker,
                    self._content_radar,
                )
                log.info("EnergyOracle initialised.")
        except Exception as exc:  # noqa: BLE001
            log.warning("EnergyOracle init failed: %s", exc)

    def _start_webhook_dispatcher(self) -> None:
        """
        Register all feature webhook handlers and start the HTTP dispatcher
        on port 5123.  Each handler guards against a None feature instance so
        a partially-initialised system still accepts webhooks safely.
        """
        from webhook_dispatcher import WebhookDispatcher

        self._dispatcher = WebhookDispatcher(port=5123)

        # ── Pulse check ──────────────────────────────────────────────────
        if self._pulse_check:
            def _handle_pulse_check(payload: dict) -> None:
                for person_key in ["conaugh", "adon"]:
                    if payload.get(f"{person_key}_home") == "true":
                        if self._pulse_check.should_check_in(person_key):
                            text = self._pulse_check.generate_check_in(person_key)
                            if text:
                                self._speak(text)
            self._dispatcher.register("aura_pulse_check", _handle_pulse_check)

        # ── Ghost DJ ─────────────────────────────────────────────────────
        if self._ghost_dj:
            def _handle_ghost_dj(payload: dict) -> None:
                suggestion = self._ghost_dj.suggest_music(
                    payload, payload.get("person")
                )
                if suggestion:
                    self._ghost_dj.apply_music(suggestion)
            self._dispatcher.register("aura_ghost_dj", _handle_ghost_dj)

        # ── Vibe sync ────────────────────────────────────────────────────
        if self._vibe_sync:
            def _handle_vibe_sync(_payload: dict) -> None:
                self._vibe_sync.poll_and_adjust()
            self._dispatcher.register("aura_vibe_sync", _handle_vibe_sync)

        # ── Social sonar ─────────────────────────────────────────────────
        if self._social_sonar:
            def _handle_social_sonar(_payload: dict) -> None:
                detection = self._social_sonar.detect_social_context()
                if (
                    detection.get("likely_guests")
                    and detection.get("confidence", 0) > 0.6
                ):
                    self._social_sonar.apply_social_mode()
            self._dispatcher.register("aura_social_sonar", _handle_social_sonar)

        # ── Weekly energy brief ──────────────────────────────────────────
        if self._energy_oracle:
            def _handle_weekly_report(_payload: dict) -> None:
                for person in ["conaugh", "adon"]:
                    text = self._energy_oracle.generate_weekly_brief(person)
                    if text:
                        self._speak(text)
                        break  # One brief per trigger is enough
            self._dispatcher.register("aura_weekly_report", _handle_weekly_report)

        # ── Generic voice prompt (HA → TTS passthrough) ──────────────────
        def _handle_voice_prompt(payload: dict) -> None:
            message = payload.get("message", "")
            if message:
                self._speak(message)
        self._dispatcher.register("aura_voice_prompt", _handle_voice_prompt)

        # ── Learning evolution cycle ─────────────────────────────────────
        if self._context is not None and hasattr(self._context, "_engine"):
            _engine_ref = self._context._engine  # noqa: SLF001 — captured for closure

            def _handle_learning_evolve(_payload: dict) -> None:
                from learning.pattern_engine import RoutineOptimizer
                optimizer = RoutineOptimizer(_engine_ref)
                suggestions = optimizer.evolve()
                log.info("Learning evolution complete: %d suggestions", len(suggestions))
            self._dispatcher.register("aura_learning_evolve", _handle_learning_evolve)

        # ── Habit auto-detection ─────────────────────────────────────────
        if self._habit_tracker:
            def _handle_habit_detect(_payload: dict) -> None:
                for person in ["conaugh", "adon"]:
                    self._habit_tracker.auto_detect_habits(person)
            self._dispatcher.register("aura_habit_detect", _handle_habit_detect)

        self._dispatcher.start()

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
            context = ctx.activity.value if ctx.activity is not None else "casual"

        if self._habit_tracker and person:
            try:
                report = self._habit_tracker.get_weekly_report(person)
                habit_data = {
                    habit: {"streak": streak, "days_missed": 0}
                    for habit, streak in report.streaks.items()
                } if report else None
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
