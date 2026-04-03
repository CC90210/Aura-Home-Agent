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
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np
import pyaudio
import requests
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
LEARNING_CONFIG_PATH = PROJECT_ROOT / "learning" / "config.yaml"

# ---------------------------------------------------------------------------
# Learning-module path setup — the learning package lives one level up.
# PROJECT_ROOT must be defined before this block.  sys.path is mutated so
# that both `person_recognition` (voice-agent/) and `learning` (project root)
# resolve correctly when the daemon starts from any working directory.
# ---------------------------------------------------------------------------
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

from person_recognition import PersonRecognizer  # noqa: E402 — after path setup
from personality import AuraPersonality  # noqa: E402 — after path setup

try:
    from learning.pattern_engine import ContextAwareness  # noqa: E402
    from learning.habit_tracker import HabitTracker  # noqa: E402
    _LEARNING_AVAILABLE = True
except ImportError:
    _LEARNING_AVAILABLE = False

_FEATURE_IMPORT_ERRORS: dict[str, str] = {}


def _optional_feature_import(module_name: str, class_name: str) -> Any | None:
    """Return an optional feature class without disabling unrelated features."""
    try:
        module = __import__(module_name, fromlist=[class_name])
        return getattr(module, class_name)
    except Exception as exc:  # noqa: BLE001
        _FEATURE_IMPORT_ERRORS[module_name] = str(exc)
        return None


MirrorMode = _optional_feature_import("mirror_mode", "MirrorMode")
AuraDrops = _optional_feature_import("aura_drops", "AuraDrops")
PulseCheck = _optional_feature_import("pulse_check", "PulseCheck")
GhostDJ = _optional_feature_import("ghost_dj", "GhostDJ")
VibeSync = _optional_feature_import("vibe_sync", "VibeSync")
DejaVu = _optional_feature_import("deja_vu", "DejaVu")
ContentRadar = _optional_feature_import("content_radar", "ContentRadar")
SocialSonar = _optional_feature_import("social_sonar", "SocialSonar")
PhantomPresence = _optional_feature_import("phantom_presence", "PhantomPresence")
EnergyOracle = _optional_feature_import("energy_oracle", "EnergyOracle")

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

if _FEATURE_IMPORT_ERRORS:
    for _module_name, _error in sorted(_FEATURE_IMPORT_ERRORS.items()):
        log.warning(
            "Optional feature module %s unavailable — related feature disabled: %s",
            _module_name,
            _error,
        )


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


class _ThreadSafeFeatureProxy:
    """Wrap a feature instance so cross-thread calls share the same lock."""

    def __init__(self, instance: Any, lock: threading.RLock) -> None:
        self._instance = instance
        self._lock = lock

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._instance, name)
        if not callable(attr):
            return attr

        def _wrapped(*args: Any, **kwargs: Any) -> Any:
            with self._lock:
                return attr(*args, **kwargs)

        return _wrapped


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
        self._learning_config: dict[str, Any] = {}
        self._personality: AuraPersonality | None = None
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
        self._feature_lock = threading.RLock()
        self._tts_lock = threading.RLock()

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
        if self._dispatcher is not None:
            try:
                self._dispatcher.stop()
            except Exception:  # noqa: BLE001
                pass
        if self._detector is not None:
            try:
                self._detector.close()
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------
    # Component initialisation
    # ------------------------------------------------------------------

    def _load_learning_config(self) -> dict[str, Any]:
        """Best-effort load of learning/config.yaml for shared runtime settings."""
        if not LEARNING_CONFIG_PATH.exists():
            log.warning(
                "learning/config.yaml not found at %s — learning features may be limited.",
                LEARNING_CONFIG_PATH,
            )
            return {}

        try:
            with LEARNING_CONFIG_PATH.open("r", encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or {}
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to load learning config from %s: %s", LEARNING_CONFIG_PATH, exc)
            return {}

        if not isinstance(raw, dict):
            log.warning("learning/config.yaml is not a mapping — ignoring.")
            return {}
        return raw

    def _resolve_shared_db_path(self) -> Path:
        """Return the shared learning DB path used by adaptive modules."""
        configured = self._learning_config.get("database", {}).get("path")
        if configured:
            return Path(str(configured))
        return PROJECT_ROOT / "data" / "patterns.db"

    def _proxy_feature(self, feature: Any) -> Any:
        """Expose a shared feature instance through the common feature lock."""
        return _ThreadSafeFeatureProxy(feature, self._feature_lock)

    def _build_intent_features(self) -> dict[str, Any]:
        """Collect all live feature modules for IntentHandler."""
        features: dict[str, Any] = {}
        if self._mirror_mode:
            features["mirror_mode"] = self._proxy_feature(self._mirror_mode)
        if self._drops:
            features["aura_drops"] = self._proxy_feature(self._drops)
        if self._pulse_check:
            features["pulse_check"] = self._proxy_feature(self._pulse_check)
        if self._ghost_dj:
            features["ghost_dj"] = self._proxy_feature(self._ghost_dj)
        if self._vibe_sync:
            features["vibe_sync"] = self._proxy_feature(self._vibe_sync)
        if self._deja_vu:
            features["deja_vu"] = self._proxy_feature(self._deja_vu)
        if self._content_radar:
            features["content_radar"] = self._proxy_feature(self._content_radar)
        if self._social_sonar:
            features["social_sonar"] = self._proxy_feature(self._social_sonar)
        if self._phantom_presence:
            features["phantom_presence"] = self._proxy_feature(self._phantom_presence)
        if self._energy_oracle:
            features["energy_oracle"] = self._proxy_feature(self._energy_oracle)
        return features

    def _normalise_person_id(self, value: Any) -> str | None:
        """Map a display name or person id to the configured canonical person id."""
        if value is None:
            return None

        raw = str(value).strip()
        if not raw:
            return None

        lowered = raw.lower()
        for person_cfg in self._learning_config.get("persons", []):
            person_id = str(person_cfg.get("id", "")).strip().lower()
            display_name = str(person_cfg.get("display_name", "")).strip().lower()
            if lowered in {person_id, display_name}:
                return person_id or None

        return lowered.replace(" ", "_")

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
        self._learning_config = self._load_learning_config()
        recognizer_config = dict(self._config)
        if self._learning_config.get("persons"):
            recognizer_config["persons"] = list(self._learning_config["persons"])

        try:
            self._personality = AuraPersonality()
            log.info("AuraPersonality initialised.")
        except Exception as exc:  # noqa: BLE001
            log.warning("AuraPersonality unavailable — greeting/pulse features limited: %s", exc)
            self._personality = None

        try:
            self._recognizer = PersonRecognizer(
                ha_url=self._secrets["ha_url"],
                ha_token=self._secrets["ha_token"],
                config=recognizer_config,
            )
            log.info("PersonRecognizer initialised.")
        except Exception as exc:  # noqa: BLE001
            log.warning("PersonRecognizer unavailable — person identification disabled: %s", exc)
            self._recognizer = None

        if _LEARNING_AVAILABLE:
            try:
                self._context = ContextAwareness(config_path=LEARNING_CONFIG_PATH)
                log.info("ContextAwareness initialised.")
            except Exception as exc:  # noqa: BLE001
                log.warning("ContextAwareness unavailable — context detection disabled: %s", exc)
                self._context = None

            try:
                self._habit_tracker = HabitTracker(config_path=LEARNING_CONFIG_PATH)
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
        self._intent = IntentHandler(
            ha_url=self._secrets["ha_url"],
            ha_token=self._secrets["ha_token"],
            anthropic_api_key=self._secrets["anthropic_api_key"],
            config=self._config,
            features=self._build_intent_features(),
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
        ha_url: str = self._secrets["ha_url"]
        ha_token: str = self._secrets["ha_token"]
        api_key: str = self._secrets["anthropic_api_key"]
        shared_db_path = self._resolve_shared_db_path()
        shared_data_dir = shared_db_path.parent

        try:
            if MirrorMode is None:
                raise RuntimeError("mirror_mode import failed")
            self._mirror_mode = MirrorMode(ha_url, ha_token, api_key)
            log.info("MirrorMode initialised.")
        except Exception as exc:  # noqa: BLE001
            log.warning("MirrorMode init failed: %s", exc)

        try:
            if AuraDrops is None:
                raise RuntimeError("aura_drops import failed")
            drops_db = shared_data_dir / "drops.db"
            self._drops = AuraDrops(ha_url, ha_token, drops_db)
            log.info("AuraDrops initialised.")
        except Exception as exc:  # noqa: BLE001
            log.warning("AuraDrops init failed: %s", exc)

        try:
            if PulseCheck is None:
                raise RuntimeError("pulse_check import failed")
            if self._habit_tracker is not None and self._personality is not None:
                personality = self._personality
                if personality is not None:
                    self._pulse_check = PulseCheck(
                        ha_url,
                        ha_token,
                        self._habit_tracker,
                        personality,
                        api_key,
                        data_dir=shared_data_dir,
                    )
                    log.info("PulseCheck initialised.")
                else:
                    log.warning("PulseCheck skipped — personality not yet loaded (intent handler not ready).")
        except Exception as exc:  # noqa: BLE001
            log.warning("PulseCheck init failed: %s", exc)

        try:
            if GhostDJ is None:
                raise RuntimeError("ghost_dj import failed")
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
            if VibeSync is None:
                raise RuntimeError("vibe_sync import failed")
            self._vibe_sync = VibeSync(ha_url, ha_token, anthropic_api_key=api_key)
            log.info("VibeSync initialised.")
        except Exception as exc:  # noqa: BLE001
            log.warning("VibeSync init failed: %s", exc)

        try:
            if DejaVu is None:
                raise RuntimeError("deja_vu import failed")
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
            if ContentRadar is None:
                raise RuntimeError("content_radar import failed")
            self._content_radar = ContentRadar(
                ha_url, ha_token,
                str(shared_db_path),
                api_key,
            )
            log.info("ContentRadar initialised.")
        except Exception as exc:  # noqa: BLE001
            log.warning("ContentRadar init failed: %s", exc)

        try:
            if SocialSonar is None:
                raise RuntimeError("social_sonar import failed")
            self._social_sonar = SocialSonar(ha_url, ha_token)
            log.info("SocialSonar initialised.")
        except Exception as exc:  # noqa: BLE001
            log.warning("SocialSonar init failed: %s", exc)

        try:
            if PhantomPresence is None:
                raise RuntimeError("phantom_presence import failed")
            if self._context is not None and hasattr(self._context, "_engine"):
                self._phantom_presence = PhantomPresence(self._context._engine)  # noqa: SLF001
                log.info("PhantomPresence initialised.")
        except Exception as exc:  # noqa: BLE001
            log.warning("PhantomPresence init failed: %s", exc)

        try:
            if EnergyOracle is None:
                raise RuntimeError("energy_oracle import failed")
            if (
                self._context is not None
                and hasattr(self._context, "_engine")
            ):
                self._energy_oracle = EnergyOracle(
                    ha_url,
                    ha_token,
                    api_key,
                    self._context._engine,  # noqa: SLF001
                    self._habit_tracker,  # may be None — EnergyOracle handles gracefully
                    self._content_radar,  # may be None — EnergyOracle handles gracefully
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
                    if self._coerce_bool(payload.get(f"{person_key}_home")):
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
                    and detection.get("confidence", 0) >= 0.6
                ):
                    self._social_sonar.apply_social_mode()
                else:
                    self._social_sonar.reset()
            self._dispatcher.register("aura_social_sonar", _handle_social_sonar)

        # ── Weekly energy brief ──────────────────────────────────────────
        if self._energy_oracle:
            def _handle_weekly_report(_payload: dict) -> None:
                for person in self._get_persons_home() or ["conaugh", "adon"]:
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
        self._dispatcher.register("aura_window_prompt", _handle_voice_prompt)

        def _handle_greet_person(payload: dict) -> None:
            person = self._normalise_person_id(payload.get("person"))
            time_of_day = payload.get("time_of_day")
            if self._personality is not None:
                greeting = self._personality.get_greeting(
                    person,
                    time_of_day=time_of_day,
                    returning_home=True,
                )
            else:
                greeting = f"Welcome back, {person or 'there'}."
            self._speak(greeting)

        self._dispatcher.register("aura_greet_person", _handle_greet_person)

        def _handle_goodnight(payload: dict) -> None:
            self._speak("Good night. Shutting everything down.")
            self._trigger_ha_webhook("aura_goodnight", payload)

        self._dispatcher.register("aura_goodnight", _handle_goodnight)

        def _handle_device_health_check(payload: dict) -> None:
            self._publish_device_health_report(payload)

        self._dispatcher.register("aura_device_health_check", _handle_device_health_check)

        # ── Learning evolution cycle ─────────────────────────────────────
        if self._context is not None and hasattr(self._context, "_engine"):
            _engine_ref = self._context._engine  # noqa: SLF001 — captured for closure

            def _handle_learning_evolve(_payload: dict) -> None:
                suggestions = _engine_ref.evolve()
                log.info("Learning evolution complete: %d suggestion(s)", suggestions)
            self._dispatcher.register("aura_learning_evolve", _handle_learning_evolve)

        # ── Habit auto-detection ─────────────────────────────────────────
        if self._habit_tracker:
            def _handle_habit_detect(_payload: dict) -> None:
                detected = self._habit_tracker.auto_detect_habits()
                log.info("Habit auto-detection complete: %s", detected)
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

        if self._deja_vu:
            with self._feature_lock:
                feedback_reply = self._deja_vu.handle_voice_feedback(
                    user_text,
                    person or "unknown",
                )
            if feedback_reply:
                self._log_event(user_text, person)
                self._speak(feedback_reply)
                return

        response_text = self._intent.process(
            user_text,
            person=person,
            context=context,
            habit_data=habit_data,
        )

        # Log the interaction for pattern learning
        if self._personality is not None and person:
            try:
                self._personality.log_speech_pattern(person, user_text)
            except Exception as exc:  # noqa: BLE001
                log.debug("Speech-pattern logging skipped: %s", exc)

        self._log_event(user_text, person)

        # ── Step 7: Speak response ──────────────────────────────────────
        self._speak(response_text)

    def _speak(self, text: str) -> None:
        """Speak ``text`` if TTS is available; otherwise log the response."""
        if not text or not text.strip():
            return

        with self._tts_lock:
            if self._tts is not None:
                self._tts.speak(text)
            else:
                log.info("[TTS disabled] Response: %r", text)

    @staticmethod
    def _coerce_bool(value: Any) -> bool:
        """Normalise JSON/template booleans from webhook payloads."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        if isinstance(value, (int, float)):
            return bool(value)
        return False

    def _get_persons_home(self) -> list[str]:
        """Return the currently-home person ids from ContextAwareness."""
        if self._context is None:
            return []
        try:
            ctx = self._context.get_current_context()
            return list(ctx.persons_home)
        except Exception as exc:  # noqa: BLE001
            log.debug("Could not resolve home persons: %s", exc)
            return []

    def _trigger_ha_webhook(self, webhook_id: str, payload: dict[str, Any]) -> bool:
        """Forward a webhook payload to Home Assistant's internal webhook API."""
        url = f"{self._secrets['ha_url']}/api/webhook/{webhook_id}"
        try:
            response = requests.post(url, json=payload, timeout=5)
            response.raise_for_status()
            return True
        except requests.RequestException as exc:
            log.warning("Failed to forward HA webhook %s: %s", webhook_id, exc)
            return False

    def _call_ha_service(
        self,
        domain: str,
        service: str,
        data: dict[str, Any],
    ) -> bool:
        """Call a Home Assistant service using the shared agent credentials."""
        url = f"{self._secrets['ha_url']}/api/services/{domain}/{service}"
        headers = {
            "Authorization": f"Bearer {self._secrets['ha_token']}",
            "Content-Type": "application/json",
        }
        try:
            response = requests.post(url, headers=headers, json=data, timeout=5)
            response.raise_for_status()
            return True
        except requests.RequestException as exc:
            log.warning("HA service %s.%s failed: %s", domain, service, exc)
            return False

    def _publish_device_health_report(self, payload: dict[str, Any]) -> None:
        """Create a persistent HA notification summarising device health."""
        devices = payload.get("devices", {})
        issues: list[str] = []
        total_devices = 0

        if isinstance(devices, dict):
            for group_devices in devices.values():
                if not isinstance(group_devices, dict):
                    continue
                for device_name, state in group_devices.items():
                    total_devices += 1
                    state_str = str(state).strip().lower()
                    if state_str in {"", "unknown", "unavailable", "offline", "none"}:
                        issues.append(f"{device_name}: {state}")

        check_time = payload.get("check_time", "just now")
        if issues:
            message = (
                f"Health check at {check_time} found {len(issues)} issue(s): "
                + ", ".join(issues[:10])
            )
        else:
            message = f"Health check at {check_time} completed successfully for {total_devices} device(s)."

        self._call_ha_service(
            "persistent_notification",
            "create",
            {
                "title": "AURA Device Health Check",
                "message": message,
                "notification_id": "aura_device_health_check",
            },
        )

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
