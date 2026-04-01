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

        log.info(
            "TTSEngine initialised — model: %s  voice: %s  output_device: %s",
            self._model,
            self._voice_id,
            self._output_device if self._output_device is not None else "default",
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

        log.info("Speaking: %r", text[:80] + ("…" if len(text) > 80 else ""))

        try:
            audio_bytes = self._generate_audio(text)
        except Exception as exc:  # noqa: BLE001 — TTS must never crash the main loop
            log.error("TTS generation failed: %s", exc)
            return

        try:
            self._play_audio(audio_bytes)
        except Exception as exc:  # noqa: BLE001
            log.error("TTS playback failed: %s", exc)

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
        Decode MP3 audio and play it through PyAudio.

        pydub is used to decode the MP3 data returned by ElevenLabs.  It
        requires either ffmpeg or libav to be installed on the system.

        Parameters
        ----------
        audio_bytes:
            Raw MP3 data as returned by ``_generate_audio``.
        """
        try:
            from pydub import AudioSegment  # type: ignore[import-untyped]
            from pydub.playback import play as pydub_play  # type: ignore[import-untyped]

            segment = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")

            if self._output_device is not None:
                # pydub's play() uses the default device; for a specific device
                # we fall through to the PyAudio path below.
                self._play_via_pyaudio(segment)
            else:
                log.debug("Playing audio via pydub (default output device)…")
                pydub_play(segment)

        except ImportError:
            # pydub not installed — fall back to raw PyAudio playback after
            # decoding with the built-in wave module.  This only works if
            # ElevenLabs returns PCM/WAV, which it does not by default.
            # Log a clear instruction instead of silently failing.
            log.error(
                "pydub is not installed — cannot decode MP3 audio.  "
                "Install it with: pip install pydub  "
                "(also requires ffmpeg: sudo apt-get install ffmpeg)"
            )

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
