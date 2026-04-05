---
description: "Debug AURA voice agent issues. Use when voice commands aren't working, intents aren't matching, or audio detection fails."
---
The voice agent is at `voice-agent/aura_voice.py` (53KB).

Debug flow:
1. Check if the voice process is running: `ps aux | grep aura_voice`
2. Check logs for errors in the voice-agent directory
3. Intent matching issues: read `voice-agent/intent_handler.py`
4. Audio detection: check PyAudio device index in clap-trigger config
5. If clap trigger not working: verify microphone permissions and PyAudio install
