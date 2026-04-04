# Wake Word Models

Place your custom `hey_aura.onnx` model here.

This model is trained by running `train_wake_word.py` on the Pi:

```bash
cd /config/aura/voice-agent
/config/aura/.venv/bin/python train_wake_word.py
```

Follow the prompts to say "Hey Aura" ~16 times. The script saves the trained
model to `models/hey_aura.onnx`. Once this file exists, the voice agent will
use it automatically instead of the built-in fallback model.

AURA uses OpenWakeWord (https://github.com/dscripka/openWakeWord) for wake
word detection — it is free, open source, and runs entirely on-device with no
cloud subscriptions or API keys required.
