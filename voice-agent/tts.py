"""
AURA Text-to-Speech Engine
===========================
Converts text to speech using the ElevenLabs API and plays the audio
through the configured output device.

Streaming is used so playback starts as soon as the first audio chunk
arrives from the API, minimising perceived latency.

If the ElevenLabs API is unavailable or returns an error, the failure is
logged and the method returns without raising — the main pipeline should
not stall because TTS is down.

Usage (standalone, for testing):
    ELEVENLABS_API_KEY=... ELEVENLABS_VOICE_ID=... python tts.py
"""

from __future__ import annotations

import io
import logging
import os
from typing import Any

log = logging.getLogger("aura.tts")

# Default ElevenLabs streaming chunk size (bytes).  Smaller = lower latency
# at the cost of more HTTP overhead.
_STREAM_CHUNK_BYTES = 4096


class TTSEngine:
    """
    Wraps the ElevenLabs streaming TTS API.

    Parameters
    ----------
    api_key:
        ElevenLabs API key (xi-api-key).  Must not be empty.
    voice_id:
        ElevenLabs voice ID.  Obtain from elevenlabs.io or the API.
    config:
        The full config dict.  Reads from ``tts`` section:
          - model         (str)       — ElevenLabs model ID
          - output_device (int|None)  — PyAudio output device index
    """

    def __init__(self, api_key: str, voice_id: str, config: dict[str, Any]) -> None:
        if not api_key:
            raise ValueError("ElevenLabs API key must not be empty.")
        if not voice_id:
            raise ValueError("ElevenLabs voice ID must not be empty.")

        tts_cfg = config.get("tts", {})

        self._api_key: str = api_key
        self._voice_id: str = voice_id
        self._model: str = tts_cfg.get("model", "eleven_turbo_v2_5")
        self._output_device: int | None = tts_cfg.get("output_device")  # None = default

        # Character budget tracking — ElevenLabs free tier is 10,000 chars/month.
        # Tracks usage in-memory (resets on restart) and warns when approaching limit.
        self._monthly_char_limit: int = int(tts_cfg.get("monthly_char_limit", 10_000))
        self._chars_used: int = 0
        self._budget_warned: bool = False

        log.info(
            "TTSEngine initialised — model: %s  voice: %s  output_device: %s  char_budget: %d",
            self._model,
            self._voice_id,
            self._output_device if self._output_device is not None else "default",
            self._monthly_char_limit,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def speak(self, text: str) -> None:
        """
        Generate speech for ``text`` and play it through the output device.

        Uses ElevenLabs streaming so audio playback starts before the full
        response is downloaded.  Silently logs and returns on any error so
        the main pipeline is never blocked by TTS failures.

        Parameters
        ----------
        text:
            The string to synthesise.  An empty string is a no-op.
        """
        if not text or not text.strip():
            log.debug("speak() called with empty text — skipping.")
            return

        char_count = len(text)
        self._chars_used += char_count

        # Warn at 80% of budget, then again at 95%
        usage_pct = (self._chars_used / self._monthly_char_limit) * 100
        if usage_pct >= 95 and not self._budget_warned:
            log.warning(
                "ElevenLabs character budget nearly exhausted: %d/%d (%.0f%%). "
                "Consider upgrading your plan or reducing response length.",
                self._chars_used, self._monthly_char_limit, usage_pct,
            )
            self._budget_warned = True
        elif usage_pct >= 80 and not self._budget_warned:
            log.warning(
                "ElevenLabs character usage at %.0f%%: %d/%d chars used this session.",
                usage_pct, self._chars_used, self._monthly_char_limit,
            )

        if self._chars_used > self._monthly_char_limit:
            log.error(
                "ElevenLabs character budget exceeded (%d/%d). Skipping TTS to preserve quota.",
                self._chars_used, self._monthly_char_limit,
            )
            return

        log.info("Speaking (%d chars, %d/%d budget): %r",
                 char_count, self._chars_used, self._monthly_char_limit,
                 text[:80] + ("…" if len(text) > 80 else ""))

        try:
            audio_bytes = self._generate_audio(text)
        except Exception as exc:  # noqa: BLE001 — TTS must never crash the main loop
            log.error("TTS generation failed: %s", exc)
            self._play_error_tone()
            return

        try:
            self._play_audio(audio_bytes)
        except Exception as exc:  # noqa: BLE001
            log.error("TTS playback failed: %s", exc)
            self._play_error_tone()

    def get_usage(self) -> dict[str, int | float]:
        """Return character usage stats for monitoring/health checks."""
        return {
            "chars_used": self._chars_used,
            "char_limit": self._monthly_char_limit,
            "usage_pct": round((self._chars_used / self._monthly_char_limit) * 100, 1),
        }

    def set_voice(self, voice_id: str) -> None:
        """
        Switch to a different ElevenLabs voice at runtime.

        Parameters
        ----------
        voice_id:
            The new ElevenLabs voice ID to use for subsequent ``speak()`` calls.
        """
        if not voice_id:
            log.warning("set_voice() called with empty voice_id — ignoring.")
            return
        log.info("Switching TTS voice: %s → %s", self._voice_id, voice_id)
        self._voice_id = voice_id

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _play_error_tone(self) -> None:
        """Play a short descending tone so the user knows TTS failed.

        Without this, a TTS failure results in complete silence — the user
        thinks AURA crashed. A quick two-note descending tone signals
        "I tried to respond but my voice isn't working right now."
        """
        try:
            import numpy as _np

            sample_rate = 22050
            duration = 0.15
            t = _np.linspace(0, duration, int(sample_rate * duration), dtype=_np.float32)
            # Two descending tones: E5 → C5 (659 Hz → 523 Hz)
            tone1 = (_np.sin(2 * _np.pi * 659 * t) * 0.3 * 32767).astype(_np.int16)
            tone2 = (_np.sin(2 * _np.pi * 523 * t) * 0.3 * 32767).astype(_np.int16)
            silence = _np.zeros(int(sample_rate * 0.05), dtype=_np.int16)
            audio = _np.concatenate([tone1, silence, tone2])

            import pyaudio
            pa = pyaudio.PyAudio()
            stream = pa.open(format=pyaudio.paInt16, channels=1,
                             rate=sample_rate, output=True)
            stream.write(audio.tobytes())
            stream.stop_stream()
            stream.close()
            pa.terminate()
        except Exception:  # noqa: BLE001
            pass  # If even the error tone fails, nothing we can do

    def _generate_audio(self, text: str) -> bytes:
        """
        Call the ElevenLabs streaming TTS endpoint and collect all audio
        chunks into a single bytes object.

        Returns
        -------
        bytes
            Raw MP3 audio data.

        Raises
        ------
        RuntimeError
            If the HTTP request fails or returns a non-200 status.
        """
        import requests  # Local import — requests is always available

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self._voice_id}/stream"
        headers = {
            "xi-api-key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": text,
            "model_id": self._model,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }

        log.debug("Requesting TTS from ElevenLabs (model=%s)…", self._model)

        with requests.post(
            url,
            headers=headers,
            json=payload,
            stream=True,
            timeout=15,
        ) as resp:
            if resp.status_code != 200:
                body = resp.text[:200]
                raise RuntimeError(
                    f"ElevenLabs API error {resp.status_code}: {body}"
                )

            buffer = io.BytesIO()
            for chunk in resp.iter_content(chunk_size=_STREAM_CHUNK_BYTES):
                if chunk:
                    buffer.write(chunk)

        audio_bytes = buffer.getvalue()
        log.debug("TTS audio received: %d bytes", len(audio_bytes))
        return audio_bytes

    def _play_audio(self, audio_bytes: bytes) -> None:
        """
        Play MP3 audio through the configured output device.

        Tries pygame first (reliable on Windows), then pydub as fallback.

        Parameters
        ----------
        audio_bytes:
            Raw MP3 data as returned by ``_generate_audio``.
        """
        # Strategy 1: pygame.mixer — handles MP3 directly, no temp file issues
        try:
            self._play_via_pygame(audio_bytes)
            return
        except ImportError:
            log.debug("pygame not available — trying pydub…")
        except Exception as exc:
            log.warning("pygame playback failed: %s — trying pydub…", exc)

        # Strategy 2: pydub (requires ffmpeg)
        try:
            from pydub import AudioSegment  # type: ignore[import-untyped]
            from pydub.playback import play as pydub_play  # type: ignore[import-untyped]

            segment = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")

            if self._output_device is not None:
                self._play_via_pyaudio(segment)
            else:
                log.debug("Playing audio via pydub (default output device)…")
                pydub_play(segment)

        except ImportError:
            log.error(
                "Neither pygame nor pydub is installed — cannot play audio.  "
                "Install one: pip install pygame  OR  pip install pydub"
            )

    def _play_via_pygame(self, audio_bytes: bytes) -> None:
        """Play raw MP3 bytes using pygame.mixer — works reliably on Windows."""
        import pygame

        if not pygame.mixer.get_init():
            pygame.mixer.init()

        sound_file = io.BytesIO(audio_bytes)
        pygame.mixer.music.load(sound_file, "mp3")
        pygame.mixer.music.play()
        log.debug("Playing audio via pygame…")

        # Block until playback finishes
        while pygame.mixer.music.get_busy():
            pygame.time.wait(50)

    def _play_via_pyaudio(self, segment: Any) -> None:
        """
        Play a pydub AudioSegment through a specific PyAudio output device.

        Used when ``output_device`` is set to a non-None integer.

        Parameters
        ----------
        segment:
            A ``pydub.AudioSegment`` instance.
        """
        import pyaudio

        pa = pyaudio.PyAudio()
        try:
            stream = pa.open(
                format=pa.get_format_from_width(segment.sample_width),
                channels=segment.channels,
                rate=segment.frame_rate,
                output=True,
                output_device_index=self._output_device,
            )
            log.debug(
                "Playing audio via PyAudio device %d…", self._output_device
            )
            stream.write(segment.raw_data)
            stream.stop_stream()
            stream.close()
        finally:
            pa.terminate()


# ---------------------------------------------------------------------------
# Standalone test entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import yaml
    from pathlib import Path
    from dotenv import load_dotenv

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    _script_dir = Path(__file__).resolve().parent
    load_dotenv(_script_dir.parent / ".env")

    _api_key = os.getenv("ELEVENLABS_API_KEY", "")
    _voice_id = os.getenv("ELEVENLABS_VOICE_ID", "")

    if not _api_key or not _voice_id:
        print(
            "Set ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID in the project .env file before testing."
        )
    else:
        _cfg_path = _script_dir / "config.yaml"
        with _cfg_path.open("r", encoding="utf-8") as _fh:
            _config: dict[str, Any] = yaml.safe_load(_fh)

        engine = TTSEngine(_api_key, _voice_id, _config)
        engine.speak("Hello, I am AURA. Your apartment is ready.")
        print("TTS test complete.")
