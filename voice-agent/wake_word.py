"""
AURA Wake Word Detector
=======================
Listens continuously on the USB microphone for the wake phrase "Hey Aura"
using Picovoice Porcupine.

Porcupine supports custom wake words — you generate a .ppn model file from
the Picovoice console (https://console.picovoice.ai) and place it at
voice-agent/models/hey-aura.ppn. The access key goes in .env as
PICOVOICE_ACCESS_KEY.

Fallback: If Porcupine is not installed or the model file is missing, falls
back to OpenWakeWord with the "hey_jarvis" built-in model. This is for
development/testing only — production always uses Porcupine with "Hey Aura".

Usage (standalone, for testing):
    python wake_word.py
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

import numpy as np
import pyaudio

log = logging.getLogger("aura.wake_word")

SCRIPT_DIR = Path(__file__).resolve().parent

try:
    from social_sonar import push_audio_rms
except ImportError:
    def push_audio_rms(_rms: float) -> None:
        """Fallback when social_sonar is unavailable."""
        return None


class WakeWordDetector:
    """
    Listens for "Hey Aura" and returns when detected.

    Supports two engines:
      - "porcupine" (default) — Picovoice Porcupine with custom .ppn model
      - "openwakeword" (fallback) — OpenWakeWord with built-in models

    Parameters
    ----------
    config:
        The full config.yaml dict. Reads wake_word and audio sections.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        ww_cfg = config.get("wake_word", {})
        audio_cfg = config.get("audio", {})

        self._engine: str = ww_cfg.get("engine", "porcupine")
        self._phrase: str = ww_cfg.get("phrase", "Hey Aura")
        self._sensitivity: float = float(ww_cfg.get("sensitivity", 0.6))

        # Porcupine-specific
        self._model_path: str = ww_cfg.get("model_path", "models/hey-aura.ppn")
        self._access_key: str = os.getenv("PICOVOICE_ACCESS_KEY", "")

        # OpenWakeWord fallback
        self._oww_model: str = ww_cfg.get("model", "hey_jarvis")
        self._oww_threshold: float = float(ww_cfg.get("threshold", 0.7))

        # Audio settings
        self._sample_rate: int = int(audio_cfg.get("sample_rate", 16000))
        self._chunk_size: int = int(audio_cfg.get("chunk_size", 512))
        self._channels: int = int(audio_cfg.get("channels", 1))

        self._detector: Any = None
        self._pyaudio: pyaudio.PyAudio | None = None
        self._stream: pyaudio.Stream | None = None

        log.info(
            "WakeWordDetector initialised — engine: %s  phrase: '%s'",
            self._engine,
            self._phrase,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def listen(self) -> bool:
        """
        Block until "Hey Aura" is detected. Returns True on detection.
        """
        self._ensure_detector_loaded()
        self._ensure_stream_open()

        log.info("Listening for '%s'…", self._phrase)
        assert self._stream is not None

        while True:
            try:
                raw = self._stream.read(self._chunk_size, exception_on_overflow=False)
            except OSError as exc:
                log.error("Microphone read error: %s — recovering…", exc)
                self._close_stream()
                time.sleep(1)
                self._ensure_stream_open()
                continue

            audio_int16 = np.frombuffer(raw, dtype=np.int16)
            if len(audio_int16) > 0:
                push_audio_rms(float(np.sqrt(np.mean(audio_int16.astype(np.float32) ** 2))))

            if self._engine == "porcupine":
                detected = self._check_porcupine(audio_int16)
            else:
                detected = self._check_oww(audio_int16)

            if detected:
                log.info("Wake word '%s' detected!", self._phrase)
                return True

    def close(self) -> None:
        """Release audio resources and detector. Safe to call multiple times."""
        self._close_stream()

        if self._detector is not None:
            if self._engine == "porcupine" and hasattr(self._detector, "delete"):
                self._detector.delete()
            self._detector = None

    # ------------------------------------------------------------------
    # Porcupine engine
    # ------------------------------------------------------------------

    def _load_porcupine(self) -> None:
        """Load the Porcupine detector with the custom 'Hey Aura' model."""
        model_full_path = SCRIPT_DIR / self._model_path

        if not self._access_key:
            log.warning(
                "PICOVOICE_ACCESS_KEY not set — cannot use Porcupine. "
                "Falling back to OpenWakeWord."
            )
            self._engine = "openwakeword"
            self._load_oww()
            return

        if not model_full_path.exists():
            log.warning(
                "Porcupine model not found at %s — falling back to OpenWakeWord. "
                "Generate the model at https://console.picovoice.ai",
                model_full_path,
            )
            self._engine = "openwakeword"
            self._phrase = "Hey Jarvis (fallback)"
            self._load_oww()
            return

        try:
            import pvporcupine  # type: ignore[import-untyped]

            self._detector = pvporcupine.create(
                access_key=self._access_key,
                keyword_paths=[str(model_full_path)],
                sensitivities=[self._sensitivity],
            )
            # Porcupine requires a specific frame length
            self._chunk_size = self._detector.frame_length
            self._sample_rate = self._detector.sample_rate
            log.info(
                "Porcupine loaded — model: %s  frame_length: %d  sample_rate: %d",
                model_full_path.name,
                self._chunk_size,
                self._sample_rate,
            )
        except ImportError:
            log.warning(
                "pvporcupine not installed — falling back to OpenWakeWord. "
                "Install with: pip install pvporcupine"
            )
            self._engine = "openwakeword"
            self._load_oww()
        except Exception as exc:
            log.error("Porcupine init failed: %s — falling back to OpenWakeWord", exc)
            self._engine = "openwakeword"
            self._load_oww()

    def _check_porcupine(self, audio_int16: np.ndarray) -> bool:
        """Run Porcupine inference on a single frame. Returns True if detected."""
        try:
            result = self._detector.process(audio_int16)
            return result >= 0  # >= 0 means a keyword was detected
        except Exception as exc:  # noqa: BLE001
            log.warning("Porcupine inference error: %s", exc)
            return False

    # ------------------------------------------------------------------
    # OpenWakeWord fallback engine
    # ------------------------------------------------------------------

    def _load_oww(self) -> None:
        """Load OpenWakeWord as a fallback detector."""
        try:
            from openwakeword.model import Model  # type: ignore[import-untyped]

            log.info("Loading OpenWakeWord model '%s' (fallback)…", self._oww_model)
            self._detector = Model(
                wakeword_models=[self._oww_model],
                inference_framework="onnx",
            )
            log.info("OpenWakeWord model loaded.")
        except ImportError:
            raise RuntimeError(
                "Neither pvporcupine nor openwakeword is installed. "
                "Install one: pip install pvporcupine  OR  pip install openwakeword"
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to load wake word model: {exc}") from exc

    def _check_oww(self, audio_int16: np.ndarray) -> bool:
        """Run OpenWakeWord inference. Returns True if confidence exceeds threshold."""
        audio_float = audio_int16.astype(np.float32) / 32768.0
        try:
            prediction = self._detector.predict(audio_float)
        except Exception as exc:  # noqa: BLE001
            log.warning("OWW prediction error: %s", exc)
            return False

        if not isinstance(prediction, dict):
            return False

        if self._oww_model in prediction:
            val = prediction[self._oww_model]
        elif prediction:
            val = next(iter(prediction.values()))
        else:
            return False

        try:
            score = float(val[-1]) if hasattr(val, "__len__") and len(val) > 0 else float(val)
            return score >= self._oww_threshold
        except (TypeError, ValueError, IndexError):
            return False

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _ensure_detector_loaded(self) -> None:
        """Load the appropriate wake word engine on first use."""
        if self._detector is not None:
            return

        if self._engine == "porcupine":
            self._load_porcupine()
        else:
            self._load_oww()

    def _ensure_stream_open(self) -> None:
        """Open the PyAudio input stream."""
        if self._stream is not None:
            return

        if self._pyaudio is None:
            self._pyaudio = pyaudio.PyAudio()

        while True:
            try:
                self._stream = self._pyaudio.open(
                    format=pyaudio.paInt16,
                    channels=self._channels,
                    rate=self._sample_rate,
                    input=True,
                    frames_per_buffer=self._chunk_size,
                )
                log.info("Audio stream opened (rate=%d, chunk=%d)", self._sample_rate, self._chunk_size)
                return
            except OSError as exc:
                log.error("Failed to open mic: %s — retrying in 5s", exc)
                time.sleep(5)

    def _close_stream(self) -> None:
        """Close the audio stream safely."""
        if self._stream is not None:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:  # noqa: BLE001
                pass
            self._stream = None

        if self._pyaudio is not None:
            try:
                self._pyaudio.terminate()
            except Exception:  # noqa: BLE001
                pass
            self._pyaudio = None


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import yaml

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    _cfg_path = SCRIPT_DIR / "config.yaml"
    with _cfg_path.open("r", encoding="utf-8") as _fh:
        _config: dict[str, Any] = yaml.safe_load(_fh)

    detector = WakeWordDetector(_config)
    print(f"Say '{detector._phrase}' to test…")
    detector.listen()
    print("Wake word detected — test complete.")
    detector.close()
