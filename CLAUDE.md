# CLAUDE.md — AURA by OASIS

## Identity

**AURA by OASIS** — *Ambient. Unified. Responsive. Automated.*

AURA is a premium AI-controlled smart living system built by Conaugh (CC) and Adon, both partners at OASIS AI Solutions. It transforms any apartment or home into a seamlessly intelligent living space where a Claude Code agent serves as the central intelligence — controlling lights, music, climate, cleaning, security, and more through clap triggers, voice commands, presence detection, and natural language.

The name AURA represents what the system creates: an ambient intelligence that surrounds and responds to you. Your space doesn't just have smart devices — it has an AURA.

This is both a personal project (CC and Adon's apartment) AND a productizable service that OASIS AI will install for clients. The repo is structured to support both use cases — a personal deployment and repeatable client installations.

---

## Residents

| Name | Role | Focus Areas |
|------|------|-------------|
| Conaugh (CC) | Full-time AI operator, DJ, content creator | AI development, music production, streaming, podcasting |
| Adon | Phone sales (debt/loan services), content creator, musician | Sales, content creation, music |

Both residents:
- Use iPhones (iCloud-based presence detection)
- Work from home primarily
- Share the same schedule: early wake-up, gym, healthy meals, content creation
- Want AURA to keep them accountable to their goals

---

## Architecture Overview

There are four layers:

### Layer 1: Raspberry Pi 5 → Home Assistant OS
- A Raspberry Pi 5 (8GB) runs Home Assistant OS — a dedicated smart home operating system
- The Pi connects to the apartment router via ethernet
- Home Assistant discovers and controls all smart devices (lights, plugs, speakers, locks, etc.)
- The Pi runs HEADLESS — no monitor needed. Access via browser at `homeassistant.local:8123`
- Home Assistant is configured via YAML files and its web UI
- The Pi is NOT a development machine — we never install IDEs or Claude Code on it

### Layer 2: MCP Server → AI Bridge
- The Model Context Protocol (MCP) connects Claude Code to Home Assistant
- **ha-mcp** (github.com/homeassistant-ai/ha-mcp) is the preferred MCP server — it provides 70+ tools for device control, automation management, dashboard creation, and system monitoring
- Alternative: Home Assistant's official built-in MCP server (simpler, fewer features)
- The MCP server runs as a Home Assistant add-on on the Pi
- Claude Code connects to it over the local WiFi network
- Once connected, Claude Code can control every exposed device via natural language

### Layer 3: Claude Code Agent + Voice Agent → The Interface
- Claude Code (running on CC's desktop via Anti-Gravity IDE) is the top-level controller
- It issues commands to Home Assistant through MCP
- It can create automations, modify scenes, query device states, troubleshoot issues
- The Voice Agent (voice-agent/) runs on the Pi as a systemd service — always listening for "Hey Aura"
- Combined with triggers (clap detection, voice, presence), it becomes the apartment's ambient intelligence — its AURA

### Layer 4: Web Dashboard → Remote Control
- A Next.js app (dashboard/) provides remote control from any phone, tablet, or browser
- Works on CC's and Adon's iPhones, iPads, and a wall-mounted tablet
- Communicates with Home Assistant via the REST API
- Hosted locally or deployed to a public URL for remote access

### Data Flow
```
CC's Desktop (Anti-Gravity / Claude Code)          Web Dashboard (Next.js)
    ↕ MCP Protocol (HTTP over local WiFi)               ↕ HA REST API
Raspberry Pi 5 (Home Assistant OS + ha-mcp add-on + Voice Agent)
    ↕ WiFi / Zigbee / Bluetooth / LAN
Smart Devices (Govee LEDs, Sonos, Smart Plugs, Locks, Cameras, etc.)
```

### Clap Trigger Flow
```
USB Microphone (plugged into Pi or separate Pi Zero)
    → Python clap_listener.py (runs as systemd service)
    → Detects double/triple/quad clap pattern
    → Fires HTTP webhook to Home Assistant
    → Home Assistant triggers corresponding scene/automation
```

---

## Technology Stack

### Software
| Component | Technology | Purpose |
|-----------|-----------|---------|
| Smart Home Hub | Home Assistant OS | Central device management and automation |
| AI Bridge | ha-mcp (MCP Server) | Connects Claude Code ↔ Home Assistant |
| Clap Detection | Python + PyAudio + NumPy | Listens for clap patterns via USB mic |
| LED Control | Govee API v2.0 (REST + LAN) | Programmatic light control |
| Speaker Control | SoCo Python library | Programmatic Sonos control |
| Music | Spotify Web API | Playlist and playback control |
| Voice Agent | OpenWakeWord + faster-whisper + Claude API + ElevenLabs | Full voice pipeline: wake word → STT → AI → TTS |
| Adaptive Learning | Python + SQLite | Pattern recognition and habit tracking |
| Web Dashboard | Next.js + Tailwind CSS + TypeScript | Remote control via phones, tablets, wall-mounted iPad |
| Person Recognition | iCloud presence + voice signatures | Identifies CC vs Adon for personalized responses |
| Custom Sensors (Phase 4) | ESPHome on ESP32 | Room-by-room environmental monitoring |
| Smart Mirror (Phase 4) | MagicMirror² | Wall-mounted info display |
| CI/CD | GitHub Actions | YAML validation on push |
| Deployment | Bash + SCP + SSH | Push configs from desktop to Pi |

### Key APIs and Their Details

#### Govee LED API
- **Auth**: API key via HTTP header `Govee-API-Key`
- **Get API Key**: Govee Home app → Profile → About → Apply for API Key (emailed instantly)
- **Base URL**: `https://developer-api.govee.com/v1`
- **Endpoints**: GET `/devices` (list devices), PUT `/devices/control` (send commands)
- **Commands**: `turn` (on/off), `brightness` (0-100), `color` (RGB object), `colorTem` (color temperature)
- **Rate Limits**: 100 requests/minute per API key
- **LAN API**: UDP multicast on port 4001/4002 for local control (faster, no rate limits)
- **Python Libraries**: `govee-api-laggat` (PyPI), `govee-led-wez` (GitHub — supports LAN + HTTP + BLE)
- **Home Assistant**: Native Govee integration + community HACS integration for LAN control
- **IMPORTANT**: Enable LAN Control in Govee app per device: Device Settings → LAN Control → Enable

#### Spotify Web API
- **Auth**: OAuth 2.0 (Client Credentials or Authorization Code flow)
- **Get Credentials**: developer.spotify.com → Create App → Client ID + Secret
- **Key Endpoints**: `/v1/me/player/play`, `/v1/me/player/pause`, `/v1/me/player/devices`
- **Home Assistant**: Built-in Spotify integration handles auth and exposes media_player entity
- **Limitation with Sonos**: Spotify API cannot directly control Sonos speakers. Workaround: use HA's media_player service with Spotify URIs through the HA Spotify integration, or use SoCo + UPnP

#### Sonos (SoCo Python Library)
- **No API key needed** — communicates over local network via UPnP
- **Install**: `pip install soco`
- **Discovery**: `soco.discover()` finds all Sonos speakers on the network
- **Key Methods**: `play_uri()`, `pause()`, `play()`, `volume`, `get_current_track_info()`
- **Party Mode**: `sonos.partymode()` — groups all speakers
- **Home Assistant**: Native Sonos integration with full media_player controls

#### Home Assistant REST API
- **Auth**: Long-Lived Access Token via Bearer header
- **Get Token**: HA web UI → Profile → Long-Lived Access Tokens → Create
- **Base URL**: `http://homeassistant.local:8123/api`
- **Key Endpoints**: GET `/states` (all device states), POST `/services/{domain}/{service}` (call a service)
- **Webhooks**: POST `/api/webhook/{webhook_id}` — used by clap detection to trigger automations

#### ha-mcp (MCP Server)
- **GitHub**: github.com/homeassistant-ai/ha-mcp
- **Install**: HA Add-on Store → Add repo URL → Install add-on
- **Claude Code connection**: `claude mcp add ha-mcp -- docker run -i --rm -e HA_URL -e HA_TOKEN voska/hass-mcp`
- **70+ tools** including: device control, automation CRUD, dashboard management, entity state queries
- **Supports**: Claude Code, Claude Desktop, Gemini CLI, ChatGPT, VS Code, Cursor

#### ElevenLabs TTS
- **Auth**: API key via `xi-api-key` header
- **Get Key**: elevenlabs.io → Profile → API Keys
- **Endpoint**: POST `https://api.elevenlabs.io/v1/text-to-speech/{voice_id}`
- **Use Case**: Give the apartment AI a voice that responds through speakers

#### Clap Detection
- **Python package**: `pi-clap` (github.com/nikhiljohn10/pi-clap)
- **Alternative**: Custom implementation using PyAudio + NumPy (what we built)
- **Node.js alternative**: `clap-detector` npm package
- **Hardware**: Any USB microphone ($10-30) + Raspberry Pi
- **Method**: Detect audio transients (sharp amplitude spikes), match against timing patterns
- **Configuration**: Threshold (amplitude sensitivity), pattern_timeout (gap between claps), cooldown (post-trigger delay)

---

## Recommended Products (Verified API/HA Support)

### Lighting
- **Govee LED Strips** (H6159, H6163) — $30-70 CAD — REST API + LAN API + HA integration
- **Philips Hue Starter Kit** — $80-180 CAD — Most mature lighting API, local Hue Bridge API
- **Nanoleaf Shapes/Elements** — $100-250 CAD — Open REST API, music reactive, wall art aesthetic
- **Govee Pixel Light Panel** — $80-120 CAD — AI-generated images via Govee app
- **Elgato Key Light** — $130-250 CAD — HTTP API for studio/content lighting

### Smart Plugs
- **TP-Link Kasa** — $15-30 CAD — python-kasa library, energy monitoring, HA native
- **Wemo Smart Plugs** — $20-35 CAD — REST API, HA native

### Speakers
- **Sonos Era 100** — $280-350 CAD — SoCo Python library, premium sound
- **Amazon Echo Dot** — $30-60 CAD — Alexa + HA integration, doubles as voice input

### Robot Vacuum
- **Roborock Q/S series** — $300-600 CAD — Full HA integration with zone cleaning
- **iRobot Roomba j-series** — $350-700 CAD — HA compatible, smart mapping

### Security
- **August WiFi Smart Lock** — $200-300 CAD — API access, auto-lock, works with existing deadbolt
- **Yale Assure Lock 2** — $200-350 CAD — Matter compatible, biometric
- **Wyze Cam v3/v4** — $25-40 CAD — RTSP stream for HA

### Blinds/Curtains
- **SwitchBot Blind Tilt/Curtain** — $50-100 CAD — BT + WiFi hub, HA integration
- **IKEA FYRTUR** — $130-200 CAD — Zigbee, HA native

### Climate
- **Ecobee Smart Thermostat** — $200-280 CAD — Open API, room sensors, HA native

### Other
- **ESP32 Dev Boards** — $5-10 each — ESPHome firmware for custom sensors
- **IKEA TRADFRI Shortcut Button** — $10-15 CAD — Physical scene trigger via Zigbee
- **Fire HD Tablet** — $50-150 CAD — Wall-mounted HA dashboard
- **MagicMirror² (DIY)** — $100-200 CAD — Pi-powered smart mirror

---

## Repo Structure

```
aura/
├── CLAUDE.md                    ← YOU ARE HERE — project instructions for Claude Code
├── README.md                    ← Public repo documentation
├── LICENSE                      ← MIT license
├── .env.example                 ← Environment variables template (copy to .env)
├── .gitignore
│
├── clap-trigger/                ← Clap detection system (deployed to Pi)
│   ├── clap_listener.py         ← Main Python script — listens for claps, fires webhooks
│   ├── config.yaml              ← Clap patterns, thresholds, webhook mappings
│   ├── requirements.txt         ← Python dependencies (pyaudio, numpy, requests, pyyaml)
│   └── clap_service.service     ← Systemd unit file for auto-start on Pi boot
│
├── home-assistant/              ← Home Assistant YAML configurations
│   ├── configuration.yaml       ← Root HA config (input_booleans, rest_commands, includes)
│   ├── automations/             ← Event-driven automation rules
│   │   ├── double_clap_toggle.yaml
│   │   ├── triple_clap_studio.yaml
│   │   ├── quad_clap_party.yaml
│   │   ├── goodnight.yaml
│   │   ├── movie_mode.yaml
│   │   ├── gaming_mode.yaml
│   │   ├── streaming_mode.yaml
│   │   ├── podcast_mode.yaml
│   │   ├── music_mode.yaml
│   │   ├── focus_mode.yaml
│   │   ├── guest_mode.yaml
│   │   ├── away_mode.yaml
│   │   ├── workout_mode.yaml
│   │   ├── presence_detection.yaml
│   │   ├── proactive_tv_detection.yaml
│   │   ├── proactive_weather_climate.yaml
│   │   ├── proactive_greeting.yaml
│   │   ├── proactive_sleep_detection.yaml
│   │   ├── proactive_energy_saver.yaml
│   │   ├── routine_morning_weekday.yaml
│   │   ├── routine_evening_wind_down.yaml
│   │   ├── routine_gym_reminder.yaml
│   │   ├── routine_meal_reminder.yaml
│   │   ├── routine_weekend_relaxed.yaml
│   │   ├── scheduled_coffee.yaml
│   │   ├── scheduled_air_purifier.yaml
│   │   ├── scheduled_weekly_report.yaml
│   │   ├── scheduled_device_check.yaml
│   │   ├── scheduled_learning_cycle.yaml
│   │   ├── scheduled_night_security.yaml
│   │   └── scheduled_content_reminder.yaml
│   ├── scenes/                  ← Preset device state snapshots
│   │   └── scenes.yaml
│   ├── scripts/                 ← Reusable HA action sequences
│   │   └── presence_simulation.yaml
│   ├── security/                ← Security hardening configs
│   │   └── ha_security.yaml
│   ├── dashboards/              ← Lovelace UI layouts
│   └── packages/                ← Device-specific config bundles
│
├── voice-agent/                 ← Full voice pipeline (deployed to Pi as systemd service)
│   ├── aura_voice.py            ← Main daemon — orchestrates full voice pipeline
│   ├── wake_word.py             ← OpenWakeWord "Hey Aura" listener
│   ├── stt.py                   ← Speech-to-text via faster-whisper
│   ├── tts.py                   ← Text-to-speech via ElevenLabs
│   ├── intent_handler.py        ← Claude API intent processing + HA action execution
│   ├── personality.py           ← AURA personality engine
│   ├── person_recognition.py    ← Identifies CC vs Adon
│   ├── capabilities.py          ← Self-help and capabilities registry
│   ├── security.py              ← Voice command security (PIN, blocked actions)
│   ├── personality.yaml         ← AURA's personality traits, slang, speech patterns
│   ├── capabilities.yaml        ← Registered capabilities and help text
│   ├── config.yaml              ← Wake word sensitivity, TTS voice IDs, thresholds
│   ├── requirements.txt         ← Python dependencies
│   └── aura_voice.service       ← Systemd unit file for auto-start on Pi boot
│
├── learning/                    ← Adaptive learning — pattern engine and habit tracker
│   ├── pattern_engine.py        ← Behavioral pattern detection + Darwinian optimization
│   ├── habit_tracker.py         ← Daily habit tracking and accountability
│   ├── config.yaml              ← Habit goals, learning thresholds, optimization params
│   ├── requirements.txt         ← Python dependencies (sqlite3, scikit-learn, etc.)
│   └── __init__.py
│
├── dashboard/                   ← Next.js web dashboard for remote control
│   ├── src/
│   │   ├── app/                 ← Next.js App Router pages and layouts
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx
│   │   │   ├── globals.css
│   │   │   ├── login/page.tsx   ← Dashboard authentication page
│   │   │   └── api/
│   │   │       ├── scene/route.ts
│   │   │       ├── service/route.ts
│   │   │       └── auth/route.ts ← Auth API endpoint
│   │   ├── components/          ← Reusable UI components
│   │   │   ├── SceneButton.tsx
│   │   │   ├── RoomCard.tsx
│   │   │   ├── NowPlaying.tsx
│   │   │   ├── ClimateControl.tsx
│   │   │   ├── HabitTracker.tsx
│   │   │   └── StatusBar.tsx
│   │   ├── lib/                 ← HA REST API client, utility functions
│   │   │   ├── ha-client.ts
│   │   │   └── types.ts
│   │   └── middleware.ts        ← Security middleware (rate limiting, auth, headers)
│   ├── package.json
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   └── next.config.ts
│
├── esp32-sensors/               ← Phase 4: Custom room sensors
├── smart-mirror/                ← Phase 4: MagicMirror² config
│
├── scripts/                     ← Setup and deployment automation
│   ├── setup/
│   │   ├── pi_setup.sh          ← First-time Pi installation script
│   │   └── verify_install.sh    ← Post-install verification
│   ├── deploy/
│   │   ├── update_configs.sh    ← Push configs to Pi
│   │   └── deploy_client.sh     ← Deploy to a specific client
│   ├── test_webhook.sh          ← Test HA webhooks manually
│   ├── test_clap.sh             ← Test clap detection locally
│   └── security_audit.sh        ← Security audit checker
│
├── clients/                     ← Client-specific configuration overrides
│   └── .template/               ← Copy this for each new client
│
├── docs/                        ← Documentation
│   ├── SETUP_GUIDE.md           ← Step-by-step from zero to working system
│   ├── SECURITY.md              ← Security hardening guide
│   ├── TROUBLESHOOTING.md       ← Common issues and fixes
│   └── CLIENT_ONBOARDING.md     ← How to deploy for a paying client
│
└── .github/workflows/
    └── validate.yml             ← CI: lint YAML + validate Python on push
```

---

## Implementation Phases

### Phase 1: Foundation — COMPLETE
- Raspberry Pi 5 + Home Assistant OS
- Govee LED strips (1-2 rooms)
- 2-3 TP-Link Kasa smart plugs
- Connect Claude Code via ha-mcp
- Basic commands working: lights on/off, colors, plug control

### Phase 2: Clap Detection + Music + Basic Scenes — COMPLETE
- USB microphone + clap_listener.py deployed as systemd service
- Double-clap toggles main scene, triple-clap toggles studio mode
- Spotify integration in HA
- Smart speaker (Sonos or Echo)
- Core scenes built: Morning, Goodnight, Party, Studio, Movie, Focus

### Phase 3: Voice Agent + Dashboard + Adaptive Learning — COMPLETE
- Full voice pipeline (voice-agent/) running on Pi as systemd service
- "Hey Aura" wake word via OpenWakeWord
- Speech-to-text via faster-whisper (local, no cloud latency)
- Intent handling via Claude API
- ElevenLabs TTS voice responses through speakers
- Person recognition (CC vs Adon) via iCloud presence
- Adaptive learning (learning/) — pattern engine + habit tracker
- Next.js web dashboard (dashboard/) accessible on phones, iPads, wall tablet
- Expanded scenes: Gaming, Streaming, DJ/Music, Podcast, Guest, Away, Workout

### Phase 4: Expand — IN PROGRESS
- Nanoleaf panels or additional Govee lights
- SwitchBot smart blinds
- Elgato Key Lights for streaming and content creation
- ESP32 sensor network (temp, humidity, motion, air quality per room)
- Robot vacuum with zone cleaning
- Smart lock + security cameras
- DIY smart mirror (Pi + MagicMirror²)

---

## Scene Definitions

### Welcome Home (Double Clap)
- Living room LEDs: warm amber (RGB 255,180,100) at 70%
- Bedroom LEDs: soft warm (RGB 255,200,150) at 40%
- Spotify playlist starts on speakers at 30% volume

### Morning Routine (Scheduled 7:30 AM weekdays)
- Lights fade in over 60 seconds to warm white 2700K
- Blinds open gradually
- Coffee maker on via smart plug
- Morning playlist at low volume
- After 5 min: lights increase to 4000K at 70%

### Studio / Content Mode (Triple Clap)
- Key light: 100% brightness, 5000K daylight
- Desk accent LEDs: blue (RGB 0,120,255) at 60%
- Room overheads: dim to 20%
- Notifications muted

### Movie Mode (Webhook)
- All lights: deep purple (RGB 30,10,80) at 5%
- Blinds close
- Speaker switches to movie audio profile

### Party Mode (Quad Clap)
- LEDs and Nanoleaf: music-reactive mode
- Speakers: 75% volume
- Overhead lights off, accent only

### Goodnight (Webhook)
- All lights fade off over 30 seconds
- Smart lock engages
- Thermostat drops to 18°C
- Music fades and stops
- Cameras arm

### Focus / Deep Work (Webhook)
- Lights: cool daylight 5000K at 80%
- Lo-fi playlist at low volume
- Notifications muted
- Air purifier to quiet mode

### Gaming Mode (Webhook / Voice)
- LEDs: dynamic color cycle or deep blue/purple (RGB 20,0,80) at 50%
- Overhead lights off
- Speaker: game audio profile, volume at 60%
- Notifications muted

### Streaming Mode (Webhook / Voice)
- Key light: 100% brightness, 5500K daylight
- Background LEDs: brand color accent (RGB 100,0,255) at 40%
- Overhead lights: dim to 15%
- Mic and camera indicators armed

### Music / DJ Mode (Quad Clap / Voice)
- LEDs and Nanoleaf: music-reactive mode
- Govee strips cycle through color palette
- Speakers: 80% volume, bass-heavy EQ profile
- Overhead lights off, accent only

### Podcast Mode (Webhook / Voice)
- Key light: 100% brightness, 4500K neutral
- Background LEDs: warm amber (RGB 255,160,80) at 30%
- Overhead lights off
- Quiet HVAC/fan mode to reduce background noise

### Guest Mode (Webhook / Voice)
- All common area lights: warm white 3000K at 60%
- Bedroom LEDs: off
- Speaker: ambient playlist at 25% volume
- Lock in unlocked state for expected guests

### Away Mode (Presence Detection → Webhook)
- All lights off
- Thermostat sets to eco temperature (16°C)
- All smart plugs off except always-on devices
- Cameras arm
- Music stops

### Workout Mode (Webhook / Voice)
- Lights: high energy — bright white 5000K at 90%
- Speakers: hype playlist at 70% volume
- Fan/air purifier on full
- Timer automation optional (rest intervals)

---

## AURA Personality

AURA has a defined personality configured in `voice-agent/personality.yaml`. Key traits:

- **Tone**: Witty, friendly, conversational — not robotic or overly formal
- **Slang**: Picks up and uses CC's and Adon's speech patterns over time (learned via pattern engine)
- **Accountability**: Proactively nudges residents on their goals (gym, meals, sleep, content schedule)
- **Awareness**: Knows who is home (CC vs Adon) and personalizes responses accordingly
- **Humor**: Dry wit, occasional banter — keeps interactions engaging
- **Brevity**: Keeps voice responses short unless detail is requested

The personality module (`voice-agent/personality.py`) loads `personality.yaml` at startup and injects the persona as a system prompt prefix when calling the Claude API. Speech patterns and learned slang are updated periodically by the pattern engine.

---

## Adaptive Learning

The `learning/` directory contains the pattern engine and habit tracker:

### Pattern Engine (`learning/pattern_engine.py`)
- Reads Home Assistant event history from SQLite
- Detects recurring behavioral patterns (e.g., "CC always starts Studio Mode at 9 PM on weekdays")
- Surfaces insights to AURA's voice agent and dashboard
- Uses a Darwinian optimization approach — patterns that consistently predict behavior are reinforced, inconsistent patterns decay

### Habit Tracker (`learning/habit_tracker.py`)
- Tracks configured goals from `learning/config.yaml` (gym check-ins, meal times, sleep schedule, content uploads)
- Sends proactive nudges via AURA's voice or dashboard notifications when residents are off-track
- Logs streaks and progress for accountability

---

## Voice Agent Pipeline

Full flow from wake word to spoken response:

```
USB Mic (Pi)
    → OpenWakeWord — detects "Hey Aura" locally
    → Record speech (voice-agent/wake_word.py)
    → faster-whisper STT — transcribes speech locally (voice-agent/stt.py)
    → Claude API — processes intent, generates response (voice-agent/intent_handler.py)
        → Optionally calls HA services (lights, music, scenes, etc.)
    → ElevenLabs TTS — converts response text to audio (voice-agent/tts.py)
    → Speaker — plays response via Sonos or connected audio output
```

Person recognition runs in parallel: `voice-agent/person_recognition.py` checks iCloud presence to determine if CC or Adon is home, and optionally uses voice signature matching to identify the speaker. The identified person is passed to the Claude API as context so responses are personalized.

---

## Web Dashboard

The `dashboard/` directory is a Next.js (App Router) application built with TypeScript and Tailwind CSS.

- **Access**: Runs on the local network (or deployed publicly) — open on any phone, iPad, or browser
- **Wall tablet**: Intended to be displayed full-time on a wall-mounted iPad or Fire HD tablet
- **CC's iPhone**: Pinned as a home screen web app for quick scene switching
- **Adon's iPhone**: Same — pinned as a home screen web app
- **Features**: Scene activation, device toggles, habit tracking view, who's home status, current music
- **HA connection**: Communicates with Home Assistant via the REST API using a Long-Lived Access Token stored in environment variables

To run locally:
```bash
cd dashboard
npm install
npm run dev
```

---

## Conventions

### File Naming
- YAML automations: `snake_case_description.yaml`
- Python scripts: `snake_case_description.py`
- Documentation: `UPPER_CASE.md`

### Home Assistant YAML
- Every automation must include: `alias`, `description`, `trigger`, `condition` (even if empty list), `action`
- Use `continue_on_error: true` on any action for a device that might not be installed yet
- Entity IDs follow HA convention: `{domain}.{area}_{device}` e.g. `light.living_room_leds`

### Secrets
- All secrets go in `.env` (never committed to git)
- Reference in scripts via environment variables
- Never hardcode API keys, tokens, or passwords in any file

### Client Deployments
- Base configs are universal — work for any installation
- Client-specific overrides go in `clients/{client_name}/`
- Never modify base configs for a specific client
- Copy `clients/.template/` for each new client

---

## Raspberry Pi Quick Reference

The Pi runs Home Assistant OS. Here's what you need to know:

- **Flash SD card**: Use Balena Etcher (balena.io/etcher) to write the HA OS image to microSD
- **First boot**: Plug in ethernet + power, wait 5-10 min, access at `homeassistant.local:8123`
- **SSH access**: Install "SSH & Web Terminal" add-on from HA Add-on Store
- **File transfer**: Use SCP from desktop: `scp file.txt root@homeassistant.local:/path/`
- **Config location on Pi**: `/config/` (this is where HA reads YAML files)
- **Restart HA**: Web UI → Settings → System → Restart, or SSH: `ha core restart`
- **View logs**: Web UI → Settings → System → Logs, or SSH: `ha core logs`
- **NO monitor, keyboard, or mouse needed** — everything is done remotely

---

## Important Commands

```bash
# SSH into the Pi
ssh root@homeassistant.local

# Test a webhook manually (e.g., simulate a double clap)
curl -X POST http://homeassistant.local:8123/api/webhook/aura_double_clap

# Check clap detection service status
ssh root@homeassistant.local 'systemctl status clap_service'

# View clap detection logs live
ssh root@homeassistant.local 'journalctl -u clap_service -f'

# Validate all YAML configs locally
python3 -c "import yaml, glob; [yaml.safe_load(open(f)) for f in glob.glob('home-assistant/**/*.yaml', recursive=True)]"

# Deploy configs to Pi
./scripts/deploy/update_configs.sh

# Deploy to a specific client
./scripts/deploy/deploy_client.sh {client_name}
```

---

## Business Context

AURA is a product under **OASIS AI Solutions**. The service tiers:

| Package | Includes | Price Range (CAD) |
|---------|----------|-------------------|
| AURA Lite | Pi + LEDs (2 rooms) + plugs + clap detection + 3 scenes | $500-800 |
| AURA Standard | + speaker + blinds + tablet dashboard + 6 scenes | $1,200-1,800 |
| AURA Pro | + smart lock + vacuum + cameras + voice + custom scenes | $2,500-4,000 |
| AURA Care | Monthly remote troubleshooting, updates, new scenes | $50-100/month |

Hardware costs are passed through at retail. Service fee covers installation, configuration, and training.

---

## Links & Resources

- Home Assistant: https://home-assistant.io
- ha-mcp: https://github.com/homeassistant-ai/ha-mcp
- Govee Developer API: https://developer.govee.com
- Govee Python library: https://github.com/wez/govee-py
- SoCo (Sonos Python): https://github.com/SoCo/SoCo
- pi-clap: https://github.com/nikhiljohn10/pi-clap
- clap-detector (Node.js): https://www.npmjs.com/package/clap-detector
- Spotify Web API: https://developer.spotify.com
- ElevenLabs: https://elevenlabs.io
- OpenWakeWord: https://github.com/dscripka/openWakeWord
- MagicMirror²: https://magicmirror.builders
- ESPHome: https://esphome.io
- Balena Etcher: https://etcher.balena.io
- OpenClaw (always-on Claude agent): https://github.com/OpenClaw