# Smart Mirror — Phase 4

MagicMirror2 configuration for a wall-mounted information display. Implementation is planned for Phase 4.

## Planned Scope

A secondary Raspberry Pi (Pi 4 or Pi Zero 2W) mounted behind a two-way mirror, running MagicMirror2 (https://magicmirror.builders). The display shows time, weather, calendar events, Home Assistant device states, and AURA status — all visible as a subtle overlay when the mirror is in use and invisible when the room is dark.

## Planned Modules

- `clock` — Time and date (built-in)
- `weather` — Current conditions and forecast using Open-Meteo (free, no API key)
- `calendar` — Google Calendar or iCal integration (built-in)
- `MMM-HomeAssistant` or `MMM-HASS` — Pull live entity states from Home Assistant (light status, temperature from ESP32 sensors, currently playing music)
- `MMM-OnSpotify` — Spotify currently playing with album art
- `MMM-AuraStatus` — Custom module (to be built) showing active AURA scene name

## Hardware Required

- Raspberry Pi 4 (2GB RAM sufficient) or Pi Zero 2W for a slimmer build
- Two-way mirror glass or acrylic (cut to size — hardware stores or online)
- Monitor or TV panel (remove from chassis to fit behind mirror)
- HDMI cable
- Slim frame (wood or metal, built or purchased)

Approximate total cost: $100–250 CAD depending on mirror size and whether you repurpose an existing monitor.

## MagicMirror2 Quick Start Reference

```bash
# Install on the mirror Pi
curl -sL https://install.mm.build | bash

# Start manually
cd ~/MagicMirror && npm start

# Run headless (SSH-controlled)
DISPLAY=:0 npm start &

# Install a community module
cd ~/MagicMirror/modules
git clone https://github.com/module-author/MMM-ModuleName
cd MMM-ModuleName && npm install
```

Configuration lives at `~/MagicMirror/config/config.js` on the mirror Pi.
