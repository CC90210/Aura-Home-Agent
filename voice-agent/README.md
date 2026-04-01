# Voice Agent — Phase 4

Voice agent with local wake word detection and spoken TTS responses. Implementation is planned for Phase 4.

## Planned Scope

**Wake word detection** using OpenWakeWord (https://github.com/dscripka/openWakeWord). The wake phrase will be "Hey Aura." Detection runs locally on the Pi — no audio is sent to an external service. When the wake word is detected, the system begins listening for a natural language command.

**Text-to-speech responses** using the ElevenLabs API (https://elevenlabs.io). AURA will respond through the connected speakers with a consistent voice, providing confirmation of commands and status updates.

## Files Planned

- `wake_word_listener.py` — Runs as a systemd service. Listens continuously for the wake phrase, then captures the following voice command and sends it to the AURA agent for processing.
- `tts_responder.py` — Accepts a text string and plays it as synthesized speech through the room's speaker via the ElevenLabs API and the Sonos or HA media player entity.

## Dependencies (when implemented)

- `openwakeword` (Python package)
- `pyaudio` (shared with clap detection)
- `requests` (for ElevenLabs API calls)
- ElevenLabs API key (stored in `.env` as `ELEVENLABS_API_KEY`)

## Environment Variables Required

```
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=
```

Obtain from https://elevenlabs.io — Profile → API Keys. The voice ID corresponds to a cloned or preset voice selected in the ElevenLabs dashboard.
