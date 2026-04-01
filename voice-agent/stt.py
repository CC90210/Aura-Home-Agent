"""
AURA Speech-to-Text
===================
Two classes that together handle post-wake-word audio capture and
transcription:

  SpeechRecorder  — records from the microphone until the user stops
                    speaking (silence detection) or a hard time limit.

  Transcriber     — converts a recorded numpy audio array to a text
                    string using faster-whisper (CPU-optimised Whisper).

faster-whisper is preferred over the standard openai-whisper package on
Raspberry Pi because it uses CTranslate2 under the hood, giving ~4× faster
inference on CPU with lower memory usage.

Usage (standalone, for testing):
    python stt.py
"""

from __future__ import annotations

import logging
import time
from typing import Any

import numpy as np
import pyaudio

log = logging.getLogger("aura.stt")


# ---------------------------------------------------------------------------
# SpeechRecorder
# ---------------------------------------------------------------------------


class SpeechRecorder:
    """
    Records audio from the default microphone until silence is detected or
    ``max_duration`` seconds have elapsed.

    The recorder uses a simple energy-based silence detector: once the RMS
    amplitude of incoming chunks has been below ``silence_threshold`` for
    ``silence_duration`` consecutive seconds, recording stops.

    Parameters
    ----------
    config:
        The full config dict.  Reads from ``audio`` section:
          - sample_rate       (int)
          - chunk_size        (int)
          - channels          (int)
          - max_record_seconds (float)
          - silence_threshold  (float)  — RMS below which chunk counts as silent
          - silence_duration   (float)  — seconds of silence before stop
    """

    def __init__(self, config: dict[str, Any]) -> None:
        audio_cfg = config["audio"]

        self._sample_rate: int = int(audio_cfg["sample_rate"])
        self._chunk_size: int = int(audio_cfg["chunk_size"])
        self._channels: int = int(audio_cfg["channels"])
        self._max_duration: float = float(audio_cfg.get("max_record_seconds", 10.0))
        self._silence_threshold: float = float(audio_cfg.get("silence_threshold", 500.0))
        self._silence_duration: float = float(audio_cfg.get("silence_duration", 1.5))

        log.info(
            "SpeechRecorder initialised — max_duration=%.1fs  "
            "silence_threshold=%.0f  silence_duration=%.2fs",
            self._max_duration,
            self._silence_threshold,
            self._silence_duration,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(self) -> np.ndarray:
        """
        Open the microphone, record until silence or timeout, then return
        the captured audio as a float32 numpy array normalised to [-1.0, 1.0].

        Returns
        -------
        np.ndarray
            1-D float32 array of audio samples at ``sample_rate`` Hz.
            Returns an empty array if no usable audio was captured.
        """
        pa = pyaudio.PyAudio()
        stream: pyaudio.Stream | None = None

        try:
            stream = self._open_stream(pa)
            frames = self._capture_frames(stream)
        except OSError as exc:
            log.error("Microphone error during recording: %s", exc)
            frames = []
        finally:
            if stream is not None:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:  # noqa: BLE001
                    pass
            try:
                pa.terminate()
            except Exception:  # noqa: BLE001
                pass

        if not frames:
            log.warning("No audio frames captured.")
            return np.array([], dtype=np.float32)

        raw = b"".join(frames)
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        duration = len(audio) / self._sample_rate
        log.info("Recorded %.2f s of audio (%d samples)", duration, len(audio))
        return audio

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _open_stream(self, pa: pyaudio.PyAudio) -> pyaudio.Stream:
        """Open and return a PyAudio input stream."""
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=self._channels,
            rate=self._sample_rate,
            input=True,
            frames_per_buffer=self._chunk_size,
        )
        log.debug(
            "Recording stream opened (rate=%d Hz, chunk=%d)",
            self._sample_rate,
            self._chunk_size,
        )
        return stream

    def _capture_frames(self, stream: pyaudio.Stream) -> list[bytes]:
        """
        Read audio chunks until silence is detected or the max duration is
        reached.  Returns a list of raw PCM byte strings.
        """
        frames: list[bytes] = []
        silence_start: float | None = None
        start_time = time.monotonic()

        while True:
            elapsed = time.monotonic() - start_time
            if elapsed >= self._max_duration:
                log.info("Max recording duration reached (%.1f s).", self._max_duration)
                break

            try:
                raw = stream.read(self._chunk_size, exception_on_overflow=False)
            except OSError as exc:
                log.warning("Audio read error during recording: %s", exc)
                break

            frames.append(raw)
            rms = self._rms(raw)

            if rms < self._silence_threshold:
                if silence_start is None:
                    silence_start = time.monotonic()
                    log.debug("Silence started (RMS=%.1f)", rms)
                elif (time.monotonic() - silence_start) >= self._silence_duration:
                    log.debug(
                        "Silence threshold met (%.2f s) — stopping recording.",
                        time.monotonic() - silence_start,
                    )
                    break
            else:
                if silence_start is not None:
                    log.debug("Speech resumed (RMS=%.1f)", rms)
                silence_start = None

        return frames

    @staticmethod
    def _rms(raw: bytes) -> float:
        """Return the RMS amplitude of a raw 16-bit PCM chunk."""
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        if samples.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(samples**2)))


# ---------------------------------------------------------------------------
# Transcriber
# ---------------------------------------------------------------------------


class Transcriber:
    """
    Converts a numpy audio array to a text string using faster-whisper.

    The model is loaded once at construction time and reused across all
    ``transcribe()`` calls to avoid the cold-start penalty on every command.

    Parameters
    ----------
    config:
        The full config dict.  Reads from ``stt`` and ``audio`` sections:
          - stt.model     (str) — Whisper model size: tiny | base | small | medium
          - stt.language  (str) — BCP-47 language code (e.g. "en")
          - audio.sample_rate (int)
    """

    def __init__(self, config: dict[str, Any]) -> None:
        stt_cfg = config["stt"]
        audio_cfg = config["audio"]

        self._model_size: str = stt_cfg.get("model", "base")
        self._language: str = stt_cfg.get("language", "en")
        self._sample_rate: int = int(audio_cfg["sample_rate"])

        self._model: Any = None  # Loaded lazily on first transcribe()

        log.info(
            "Transcriber initialised — whisper model: %s  language: %s",
            self._model_size,
            self._language,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def transcribe(self, audio: np.ndarray) -> str:
        """
        Transcribe ``audio`` to text.

        Parameters
        ----------
        audio:
            1-D float32 numpy array, normalised to [-1.0, 1.0], recorded at
            the configured ``sample_rate``.

        Returns
        -------
        str
            The transcribed text, stripped of leading/trailing whitespace.
            Returns an empty string if the audio is too short or silent.
        """
        if audio is None or len(audio) == 0:
            log.warning("transcribe() called with empty audio — returning empty string.")
            return ""

        # Require at least 0.3 s of audio to attempt transcription
        min_samples = int(self._sample_rate * 0.3)
        if len(audio) < min_samples:
            log.warning(
                "Audio too short (%d samples, need %d) — skipping transcription.",
                len(audio),
                min_samples,
            )
            return ""

        self._ensure_model_loaded()
        assert self._model is not None

        log.debug("Transcribing %.2f s of audio…", len(audio) / self._sample_rate)
        t0 = time.monotonic()

        try:
            segments, info = self._model.transcribe(
                audio,
                language=self._language,
                beam_size=5,
                vad_filter=True,  # Skip silent sections automatically
                vad_parameters={"min_silence_duration_ms": 500},
            )

            # faster-whisper returns a generator; materialise it
            text = " ".join(seg.text for seg in segments).strip()

        except Exception as exc:  # noqa: BLE001 — Whisper can raise on bad audio
            log.error("Transcription failed: %s", exc, exc_info=True)
            return ""

        elapsed = time.monotonic() - t0
        log.info(
            "Transcription complete in %.2f s (detected language: %s, prob=%.2f): %r",
            elapsed,
            info.language,
            info.language_probability,
            text,
        )
        return text

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_model_loaded(self) -> None:
        """Load the faster-whisper model on first use."""
        if self._model is not None:
            return

        try:
            from faster_whisper import WhisperModel  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                "faster-whisper is not installed.  Run: pip install faster-whisper"
            ) from exc

        log.info("Loading Whisper model '%s' — this may take a moment on first run…", self._model_size)
        t0 = time.monotonic()

        # Use int8 quantisation for CPU inference — fastest on Pi 5 without
        # significant accuracy loss on conversational speech.
        self._model = WhisperModel(
            self._model_size,
            device="cpu",
            compute_type="int8",
        )

        log.info("Whisper model loaded in %.2f s.", time.monotonic() - t0)


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

    recorder = SpeechRecorder(_config)
    transcriber = Transcriber(_config)

    print("Speak now — recording will stop after 1.5 s of silence…")
    _audio = recorder.record()
    if len(_audio) > 0:
        _text = transcriber.transcribe(_audio)
        print(f"Transcription: {_text!r}")
    else:
        print("No audio captured.")
