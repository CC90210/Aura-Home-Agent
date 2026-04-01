# AURA by OASIS

<!-- Logo placeholder: replace with /docs/assets/aura-logo.png when available -->

**Ambient. Unified. Responsive. Automated.**

AURA by OASIS transforms any apartment or home into an AI-controlled smart living space. A Claude Code agent serves as the central intelligence, controlling lights, music, climate, cleaning, security, and more through clap triggers, voice commands, presence detection, and natural language. Your space does not just have smart devices — it has an AURA.

---

## Architecture

```
CC's Desktop (Anti-Gravity / Claude Code)
    |  MCP Protocol (HTTP over local WiFi)
    v
Raspberry Pi 5 (Home Assistant OS + ha-mcp add-on)
    |  WiFi / Zigbee / Bluetooth / LAN
    v
Smart Devices (Govee LEDs, Sonos, Smart Plugs, Locks, Cameras, etc.)
```

Three layers work in concert:

- **Layer 1 — Home Assistant OS on Raspberry Pi 5**: The hub. Discovers and controls all smart devices. Runs headless, accessible at `homeassistant.local:8123`.
- **Layer 2 — ha-mcp (MCP Server)**: The bridge. Connects Claude Code to Home Assistant over the local network, exposing 70+ device control tools.
- **Layer 3 — Claude Code Agent**: The intelligence. Issues commands, creates automations, responds to triggers, and serves as the apartment's ambient AI.

---

## Features

- **Clap triggers**: Double, triple, and quad clap patterns fire distinct scenes (welcome home, studio mode, party mode, goodnight)
- **Scene control**: Pre-defined and custom scenes for morning, focus, movie, party, and more — all controllable via natural language
- **Multi-room lighting**: Govee LED strips, Nanoleaf panels, and Philips Hue controlled independently or as a unified environment
- **Music integration**: Spotify and Sonos control via Home Assistant, including room grouping and playlist automation
- **Presence detection**: Phone-based WiFi and Bluetooth beacon detection for automatic arrival and departure routines
- **Voice commands (Phase 4)**: Always-on wake word detection ("Hey Aura") with ElevenLabs TTS responses through speakers
- **Client deployable**: Base configurations are universal. Client-specific overrides are isolated in `clients/{client_name}/` for repeatable OASIS installations

---

## Quick Start

See the full step-by-step guide: [docs/SETUP_GUIDE.md](docs/SETUP_GUIDE.md)

At a high level:

1. Flash Home Assistant OS to a microSD card using Balena Etcher
2. Boot the Raspberry Pi 5 and access Home Assistant at `homeassistant.local:8123`
3. Install the ha-mcp add-on from the HA Add-on Store
4. Copy `.env.example` to `.env` and fill in your API keys and tokens
5. Connect Claude Code to ha-mcp: `claude mcp add ha-mcp -- docker run -i --rm -e HA_URL -e HA_TOKEN voska/hass-mcp`
6. Deploy the clap detection service to the Pi: `./scripts/deploy/update_configs.sh`

---

## Hardware Requirements

| Component | Recommended | Notes |
|-----------|-------------|-------|
| Hub | Raspberry Pi 5 (8GB) | Runs Home Assistant OS headless |
| Storage | 32GB+ microSD or USB SSD | SSD preferred for longevity |
| Microphone | Any USB microphone | Required for clap detection |
| Lighting | Govee LED strips (H6159/H6163) | Enable LAN Control in Govee app |
| Speakers | Sonos Era 100 | SoCo Python library for control |
| Smart plugs | TP-Link Kasa EP25 | python-kasa, energy monitoring |
| Network | Wired ethernet to Pi | WiFi works but ethernet is preferred |

See [docs/PRODUCT_LIST.md](docs/PRODUCT_LIST.md) for the full hardware list with CAD pricing.

---

## Project Structure

```
aura/
├── CLAUDE.md                    # Project instructions for Claude Code agent
├── README.md                    # This file
├── LICENSE                      # MIT license
├── .env.example                 # Environment variables template
├── .gitignore
│
├── clap-trigger/                # Clap detection system (deployed to Pi)
│   ├── clap_listener.py         # Main script — listens for claps, fires webhooks
│   ├── config.yaml              # Clap patterns, thresholds, webhook mappings
│   ├── requirements.txt         # Python dependencies
│   └── clap_service.service     # Systemd unit file for auto-start on boot
│
├── home-assistant/              # Home Assistant YAML configurations
│   ├── automations/             # Event-driven automation rules
│   ├── scenes/                  # Preset device state snapshots
│   ├── scripts/                 # Reusable HA action sequences
│   ├── dashboards/              # Lovelace UI layouts
│   └── packages/                # Device-specific config bundles
│
├── voice-agent/                 # Phase 4: Wake word + TTS voice control
│   ├── aura_voice.py            # Main entry point — orchestrates all voice agent components
│   ├── wake_word.py             # OpenWakeWord listener ("Hey Aura" detection)
│   ├── stt.py                   # Speech-to-text via faster-whisper (local) or Whisper API
│   ├── tts.py                   # Text-to-speech via ElevenLabs API
│   ├── intent_handler.py        # Claude API intent parsing → Home Assistant actions
│   ├── config.yaml              # Wake word model, STT settings, voice ID, HA webhook map
│   ├── requirements.txt         # Python deps (openwakeword, faster-whisper, anthropic, etc.)
│   └── aura_voice.service       # Systemd unit file for auto-start on Pi boot
│
├── esp32-sensors/               # Phase 4: Custom ESPHome room sensors
├── smart-mirror/                # Phase 4: MagicMirror2 configuration
│
├── scripts/
│   ├── setup/                   # First-time installation scripts
│   └── deploy/                  # Push configs to Pi, deploy to clients
│
├── clients/                     # Client-specific configuration overrides
│   └── .template/               # Copy this for each new client installation
│
├── docs/
│   ├── SETUP_GUIDE.md
│   ├── PRODUCT_LIST.md
│   ├── TROUBLESHOOTING.md
│   └── CLIENT_ONBOARDING.md
│
└── .github/workflows/
    └── validate.yml             # CI: lint YAML + validate Python on push
```

---

## Service Tiers

AURA is a productized installation service offered by OASIS AI Solutions.

| Package | Includes | Price (CAD) |
|---------|----------|-------------|
| AURA Lite | Pi + LEDs (2 rooms) + smart plugs + clap detection + 3 scenes | $500 - $800 |
| AURA Standard | + speaker + smart blinds + tablet dashboard + 6 scenes | $1,200 - $1,800 |
| AURA Pro | + smart lock + robot vacuum + cameras + voice control + custom scenes | $2,500 - $4,000 |
| AURA Care | Monthly remote troubleshooting, updates, and new scenes | $50 - $100/month |

Hardware costs are passed through at retail. Service fee covers installation, configuration, and client training.

---

## License

MIT License. See [LICENSE](LICENSE) for details.

---

Built by OASIS AI Solutions.
