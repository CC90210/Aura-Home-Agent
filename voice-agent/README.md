# Voice Agent — Phase 4

Voice agent with local wake word detection and spoken TTS responses. Implementation is planned for Phase 4.

## Planned Scope

**Wake word detection** using OpenWakeWord (https://github.com/dscripka/openWakeWord). The wake phrase will be "Hey Aura." Detection runs locally on the Pi — no audio is sent to an external service. When the wake word is detected, the system begins listening for a natural language command.

**Text-to-speech responses** using the ElevenLabs API (https://elevenlabs.io). AURA will respond through the connected speakers with a consistent voice, providing confirmation of commands and status updates.

## Files

- `wake_word.py` — Runs inside the voice agent service. Listens continuously for the wake phrase before the command recording stage begins.
- `tts.py` — Accepts text and plays synthesized speech through the configured speaker via the ElevenLabs API.

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
