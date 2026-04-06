"""
AURA Wake Word Detector
=======================
Listens continuously on the USB microphone for "Hey Aura" using
OpenWakeWord with a custom-trained model.

The custom model is trained by running train_wake_word.py on the Pi —
you say "Hey Aura" ~16 times and the script generates models/hey_aura.onnx.
No cloud services, no subscriptions, completely free.

If the custom model doesn't exist yet, falls back to the built-in
"hey_jarvis" model for development/testing.

Usage (standalone test):
    python wake_word.py
"""

from __future__ import annotations

import logging
import threading
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
        return None


class WakeWordDetector:
    """
    Listens for "Hey Aura" and returns when detected.

    Uses OpenWakeWord with either a custom-trained model (models/hey_aura.onnx)
    or the built-in "hey_jarvis" model as a fallback.
    """

    def __init__(
        self,
        config: dict[str, Any],
        suppress_event: threading.Event | None = None,
    ) -> None:
        # When set, the detector discards mic chunks instead of scoring them.
        # aura_voice.py sets this during TTS playback to prevent AURA's own
        # voice from triggering the wake word (feedback loop prevention).
        self._suppress_event = suppress_event

        ww_cfg = config.get("wake_word", {})
        audio_cfg = config.get("audio", {})

        self._phrase: str = ww_cfg.get("phrase", "Hey Aura")
        self._threshold: float = float(ww_cfg.get("threshold", 0.6))
        self._cooldown_seconds: float = float(ww_cfg.get("cooldown", 2.0))
        self._last_detection: float = 0.0

        # Try custom model first, fall back to built-in
        custom_path = ww_cfg.get("custom_model_path", "models/hey_aura.onnx")
        self._custom_model_path: Path = SCRIPT_DIR / custom_path
        self._fallback_model: str = ww_cfg.get("fallback_model", "hey_jarvis")

        # Determine which model to use
        if self._custom_model_path.exists():
            self._model_name: str = str(self._custom_model_path)
            self._using_custom = True
            log.info("Custom 'Hey Aura' model found at %s", self._custom_model_path)
        else:
            self._model_name = self._fallback_model
            self._using_custom = False
            log.warning(
                "Custom 'Hey Aura' model not found at %s — using '%s' fallback. "
                "Run 'python train_wake_word.py' on the Pi to train the custom model.",
                self._custom_model_path,
                self._fallback_model,
            )

        # Audio config
        self._sample_rate: int = int(audio_cfg.get("sample_rate", 16000))
        self._chunk_size: int = int(audio_cfg.get("chunk_size", 1280))
        self._channels: int = int(audio_cfg.get("channels", 1))

        self._model: Any = None
        self._pyaudio: pyaudio.PyAudio | None = None
        self._stream: pyaudio.Stream | None = None

        log.info(
            "WakeWordDetector — phrase: '%s'  model: %s  threshold: %.2f",
            self._phrase,
            "custom" if self._using_custom else self._fallback_model,
            self._threshold,
        )

    def listen(self) -> bool:
        """Block until "Hey Aura" is detected. Returns True."""
        self._ensure_model_loaded()
        self._ensure_stream_open()

        log.info("Listening for '%s'…", self._phrase)
        assert self._stream is not None

        while True:
            try:
                raw = self._stream.read(self._chunk_size, exception_on_overflow=False)
            except OSError as exc:
                log.error("Mic read error: %s — recovering…", exc)
                self._close_stream()
                time.sleep(1)
                self._ensure_stream_open()
                continue

            # Discard this chunk if TTS is currently playing so AURA's own
            # voice cannot trigger the wake word (acoustic feedback loop).
            if self._suppress_event is not None and self._suppress_event.is_set():
                continue

            audio_int16 = np.frombuffer(raw, dtype=np.int16)
            if len(audio_int16) > 0:
                push_audio_rms(float(np.sqrt(np.mean(audio_int16.astype(np.float32) ** 2))))

            # OpenWakeWord expects float32 in [-1.0, 1.0]
            audio_float = audio_int16.astype(np.float32) / 32768.0

            try:
                prediction = self._model.predict(audio_float)
            except Exception as exc:  # noqa: BLE001
                log.warning("Prediction error: %s", exc)
                continue

            score = self._extract_score(prediction)
            if score >= self._threshold:
                now = time.monotonic()
                if (now - self._last_detection) < self._cooldown_seconds:
                    log.debug(
                        "Wake word cooldown active — ignoring detection (%.1fs since last)",
                        now - self._last_detection,
                    )
                    continue
                self._last_detection = now
                log.info("Wake word detected! confidence=%.3f", score)
                return True

    def close(self) -> None:
        """Release resources. Safe to call multiple times."""
        self._close_stream()

    def _ensure_model_loaded(self) -> None:
        if self._model is not None:
            return

        try:
            from openwakeword.model import Model  # type: ignore[import-untyped]

            if self._using_custom:
                log.info("Loading custom 'Hey Aura' model…")
                self._model = Model(
                    wakeword_models=[str(self._custom_model_path)],
                    inference_framework="onnx",
                )
            else:
                log.info("Loading built-in '%s' model…", self._fallback_model)
                self._model = Model(
                    wakeword_models=[self._fallback_model],
                    inference_framework="onnx",
                )
            log.info("Wake word model loaded.")
        except ImportError:
            raise RuntimeError(
                "openwakeword is not installed. Run: pip install openwakeword"
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to load wake word model: {exc}") from exc

    def _ensure_stream_open(self) -> None:
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

    def _extract_score(self, prediction: dict[str, Any]) -> float:
        """Extract confidence score from OpenWakeWord prediction dict."""
        if not isinstance(prediction, dict):
            return 0.0

        # Try exact model name match, then take first value
        model_key = self._model_name if not self._using_custom else Path(self._model_name).stem
        if model_key in prediction:
            val = prediction[model_key]
        elif prediction:
            val = next(iter(prediction.values()))
        else:
            return 0.0

        try:
            if hasattr(val, "__len__") and len(val) > 0:
                return float(val[-1])
            return float(val)
        except (TypeError, ValueError, IndexError):
            return 0.0


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
