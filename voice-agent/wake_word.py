"""
AURA Wake Word Detector
=======================
Listens continuously on the default USB microphone for the wake phrase
"Hey Aura" using OpenWakeWord.  Returns control to the caller as soon as
the configured confidence threshold is exceeded.

The built-in "hey_jarvis" model is used as a stand-in for "Hey Aura" until
a custom model is trained.  To train a custom "hey_aura" model, see:
  https://github.com/dscripka/openWakeWord#training-custom-models

Usage (standalone, for testing):
    python wake_word.py
"""

from __future__ import annotations

import logging
import time
from typing import Any

import numpy as np
import pyaudio

log = logging.getLogger("aura.wake_word")

try:
    from social_sonar import push_audio_rms
except ImportError:
    def push_audio_rms(_rms: float) -> None:
        """Fallback when social_sonar is unavailable."""
        return None


class WakeWordDetector:
    """
    Wraps the OpenWakeWord library to provide a simple blocking ``listen()``
    call.  Audio is read from the default system microphone in chunks and fed
    to the model on each iteration.

    Parameters
    ----------
    config:
        The ``wake_word`` section of config.yaml, plus the ``audio`` section.
        Expected keys:
          - wake_word.model      (str)   — OWW model name or path
          - wake_word.threshold  (float) — minimum confidence to trigger
          - audio.sample_rate    (int)
          - audio.chunk_size     (int)
          - audio.channels       (int)
    """

    def __init__(self, config: dict[str, Any]) -> None:
        ww_cfg = config["wake_word"]
        audio_cfg = config["audio"]

        self._model_name: str = ww_cfg.get("model", "hey_jarvis")
        self._threshold: float = float(ww_cfg.get("threshold", 0.7))

        self._sample_rate: int = int(audio_cfg["sample_rate"])
        self._chunk_size: int = int(audio_cfg["chunk_size"])
        self._channels: int = int(audio_cfg["channels"])

        self._model: Any = None  # Loaded lazily on first listen()
        self._pyaudio: pyaudio.PyAudio | None = None
        self._stream: pyaudio.Stream | None = None

        log.info(
            "WakeWordDetector initialised — model: %s  threshold: %.2f",
            self._model_name,
            self._threshold,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def listen(self) -> bool:
        """
        Block until the wake word is detected with confidence >= threshold.

        Opens the microphone, runs inference on each audio chunk, and returns
        ``True`` the moment the model scores above the threshold.  Never
        returns ``False`` under normal operation — callers should treat the
        return value as a signal to proceed with command recording.

        Returns
        -------
        bool
            Always ``True`` when wake word is confirmed.
        """
        self._ensure_model_loaded()
        self._ensure_stream_open()

        log.info("Listening for wake word '%s'…", self._model_name)
        assert self._stream is not None

        while True:
            try:
                raw = self._stream.read(self._chunk_size, exception_on_overflow=False)
            except OSError as exc:
                log.error("Microphone read error: %s — attempting recovery…", exc)
                self._close_stream()
                time.sleep(1)
                self._ensure_stream_open()
                continue

            # OpenWakeWord expects float32 audio in range [-1.0, 1.0]
            audio_int16 = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
            if len(audio_int16) > 0:
                push_audio_rms(float(np.sqrt(np.mean(audio_int16 ** 2))))
            audio_float = audio_int16 / 32768.0

            try:
                prediction = self._model.predict(audio_float)
            except Exception as exc:  # noqa: BLE001 — OWW can raise on bad input
                log.warning("Wake word model prediction error: %s", exc)
                continue

            score = self._extract_score(prediction)
            if score >= self._threshold:
                log.info(
                    "Wake word detected! confidence=%.3f (threshold=%.2f)",
                    score,
                    self._threshold,
                )
                return True

    def close(self) -> None:
        """Release audio resources.  Safe to call multiple times."""
        self._close_stream()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_model_loaded(self) -> None:
        """Load the OpenWakeWord model on first use."""
        if self._model is not None:
            return

        try:
            from openwakeword.model import Model  # type: ignore[import-untyped]

            log.info("Loading OpenWakeWord model '%s'…", self._model_name)
            self._model = Model(wakeword_models=[self._model_name], inference_framework="onnx")
            log.info("Wake word model loaded.")
        except ImportError as exc:
            raise RuntimeError(
                "openwakeword is not installed.  Run: pip install openwakeword"
            ) from exc
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load wake word model '{self._model_name}': {exc}"
            ) from exc

    def _ensure_stream_open(self) -> None:
        """Open the PyAudio input stream, retrying on transient failures."""
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
                log.info(
                    "Wake word audio stream opened (rate=%d Hz, chunk=%d samples)",
                    self._sample_rate,
                    self._chunk_size,
                )
                return
            except OSError as exc:
                log.error(
                    "Failed to open microphone for wake word detection: %s — retrying in 5 s",
                    exc,
                )
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

    def _extract_score(self, prediction: dict[str, Any]) -> float:
        """
        Pull the confidence score for the configured model out of the OWW
        prediction dict.  OWW returns scores keyed by model name; if the key
        is absent (e.g. model name mismatch) we return 0.0.
        """
        if not isinstance(prediction, dict):
            return 0.0

        # OWW keys are the model name; look for an exact match first, then
        # fall back to the first value in the dict if only one model is loaded.
        if self._model_name in prediction:
            val = prediction[self._model_name]
        elif prediction:
            val = next(iter(prediction.values()))
        else:
            return 0.0

        # OWW returns a numpy array (one score per frame); take the last element.
        # Fall back to direct float conversion for scalar values.
        try:
            if hasattr(val, "__len__") and len(val) > 0:
                return float(val[-1])
            return float(val)
        except (TypeError, ValueError, IndexError):
            return 0.0


# ---------------------------------------------------------------------------
# Standalone test entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import yaml
    from pathlib import Path

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    _cfg_path = Path(__file__).resolve().parent / "config.yaml"
    with _cfg_path.open("r", encoding="utf-8") as _fh:
        _config: dict[str, Any] = yaml.safe_load(_fh)

    detector = WakeWordDetector(_config)
    print("Say 'Hey Jarvis' (or your configured wake word) to test…")
    detector.listen()
    print("Wake word detected — test complete.")
    detector.close()
