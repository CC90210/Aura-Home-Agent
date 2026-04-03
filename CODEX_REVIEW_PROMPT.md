# AURA Codebase — Codex Review Prompt

You are reviewing the AURA smart home AI system. This is a production codebase that will run on a Raspberry Pi 5 with Home Assistant OS, controlling physical devices (lights, speakers, locks, cameras) in a Montreal apartment. Two residents (Conaugh/CC and Adon) will use it daily.

The system was built by Claude Opus across multiple sessions and has been through two full audit passes (one internal, one adversarial Codex review). All Critical and High issues from the adversarial review have been fixed. Your job is to verify the fixes, find anything that was missed, and confirm the system is production-ready for hardware deployment.

---

## Architecture

```
CC's Desktop (Claude Code / Anti-Gravity IDE)
    ↕ MCP Protocol (HTTP over local WiFi)
Raspberry Pi 5 (Home Assistant OS + ha-mcp add-on + Voice Agent + Clap Detector)
    ↕ WiFi / Bluetooth / LAN
Smart Devices (3x Echo Dot, Govee LEDs/Plugs/Bulbs/Lamp, USB Mic)
```

**Four layers:**
1. **Home Assistant OS** on Pi 5 — device hub, 40 YAML automations, input_booleans for mode tracking
2. **Python voice-agent** — 20 modules running as systemd service: wake word → STT → Claude API → HA actions → ElevenLabs TTS
3. **Python webhook dispatcher** — HTTP server on port 5123, receives callbacks from HA automations
4. **Next.js dashboard** — deployed to Vercel, accessed from iPhones as PWA

---

## Hardware (ordered, not yet delivered)

| Device | Entity ID | Count |
|--------|-----------|-------|
| Pi 5 (8GB) | N/A | 1 |
| CMTECK USB Mic | N/A | 1 |
| Echo Dot 5th Gen | media_player.living_room_speaker, bedroom_speaker, studio_speaker | 3 |
| Govee LED Strip | light.living_room_leds | 1 |
| Govee Neon Rope | light.tv_backlight_leds | 1 |
| Govee Floor Lamp | light.desk_accent | 1 |
| Govee Smart Bulbs | light.overhead | 1 |
| Govee Smart Plugs | switch.coffee_maker, switch.air_purifier, +2 spare | 4 |
| Cat6 Ethernet | N/A | 1 |

Echo Dots are controlled via HA (Alexa Media Player HACS integration). AURA is the only voice assistant — Alexa is only used for initial Echo Dot setup. Spotify is the music source.

---

## What Was Fixed Today (18 commits)

### Critical Security Fixes
- **Goodnight webhook infinite recursion** — handler was re-triggering its own webhook. Fixed to use direct HA scene.turn_on call.
- **Webhook actions bypassed PIN security** — sensitive webhooks (lock, away, close_down) now route through PIN verification before firing.
- **Protocol webhooks hit wrong endpoint** — Claude's scene commands were POSTing to localhost:5123 (Python dispatcher, 404) instead of HA webhook endpoint. Fixed to POST to {ha_url}/api/webhook/{id}.
- **Voice PIN in plaintext** — env var is now the only supported path.
- **Database path crashed on dev machines** — changed to relative path, resolved at runtime.

### Architecture Improvements
- **Shared HA client** (voice-agent/ha_client.py) — connection pooling, thread-safe, retries. Replaces ~500 lines of duplicated HTTP code across 8 modules.
- **Shared types** (voice-agent/types.py) — TypedDict definitions for all module return types.
- **Tiered Claude models** — Haiku for routine tasks (intent parsing, playlist selection), Sonnet for creative (lighting design, weekly reports). Configured in config.yaml, resolved at startup.
- **Speaker groups** — group.aura_speakers in HA config, speakers section in voice-agent/config.yaml. Add/swap speakers by editing 2 files.
- **CSS design tokens** — 28 custom properties in globals.css. One brand color change updates entire dashboard.

### Dashboard
- Intelligence Hub moved to System tab (Home tab is now clean)
- 5 Intelligence Hub components rewritten from Tailwind (broken) to inline styles
- All mock data replaced with clean empty states (no fake data)
- Real Montreal weather via Open-Meteo API (free, no key)
- Fixed false "Connected" status (was checking HTTP 200, now reads JSON body)
- Scene cards uniform squares on iOS Safari (div instead of button)
- Mobile UI optimized (safe area insets, 44px tap targets, touch feedback)
- PWA icons generated (orbital A logo on iPhone home screen)
- Quick actions wired to real functions (tab navigation, scene webhooks)
- Middleware auth bypass for PWA assets (sw.js, icons, manifest)
- Rate limiter memory leak fixed (cleanup sweep)
- Health endpoint now references real input_boolean entities

---

## What to Verify

### 1. Python — Constructor Alignment
Read voice-agent/aura_voice.py and verify every module instantiation matches the constructor:
- GhostDJ(ha_url, ha_token, context_awareness, anthropic_api_key, speaker_entity, claude_model)
- VibeSync(ha_url, ha_token, anthropic_api_key, config, claude_model)
- SocialSonar(ha_url, ha_token, speaker_entity)
- MirrorMode(ha_url, ha_token, anthropic_api_key, claude_model)
- EnergyOracle(ha_url, ha_token, anthropic_api_key, pattern_engine, habit_tracker, content_radar, claude_model)
- PulseCheck(ha_url, ha_token, habit_tracker, personality, anthropic_api_key, data_dir, ..., claude_model)
- ContentRadar(ha_url, ha_token, db_path, anthropic_api_key, claude_model)

### 2. Python — Security
- Read voice-agent/security.py — verify PIN hashing, blocked actions list, sensitive actions list
- Read voice-agent/intent_handler.py — verify SENSITIVE_WEBHOOKS bypass is properly gated
- Verify no API keys are logged (search for log statements that might include tokens)

### 3. YAML — Webhook Alignment
Cross-reference:
- Webhook IDs in home-assistant/automations/*.yaml
- Webhook registrations in voice-agent/aura_voice.py (_dispatcher.register calls)
- Webhook IDs in dashboard/src/app/page.tsx (scene button webhook_ids)
- rest_command.aura_webhook URL in home-assistant/configuration.yaml

### 4. Dashboard — API Security
- Verify HA_TOKEN never reaches the browser (should only be in server-side API routes)
- Verify middleware protects all routes except login, static assets, and PWA files
- Verify health endpoint reads ha_connected from JSON body, not HTTP status

### 5. Data Flow End-to-End
Trace these flows:
- Dashboard scene button → /api/scene → HA webhook → automation fires
- Voice command → wake_word → stt → Claude API → intent_handler → HA action
- HA automation → rest_command → webhook_dispatcher:5123 → Python feature module
- Clap pattern → clap_listener → HA webhook → automation fires

### 6. Deployment
- verify_install.sh, pi_setup.sh, wizard.sh, full_deploy.sh, deploy_services.sh — do they all use /config/aura/ paths?
- Do .service files reference the correct venv and script paths?

---

## Key Files to Read

| Priority | File | What It Does |
|----------|------|-------------|
| 1 | voice-agent/aura_voice.py | Main orchestrator — creates all modules, registers webhooks |
| 2 | voice-agent/intent_handler.py | Claude API integration — parses voice commands, executes actions |
| 3 | voice-agent/config.yaml | All runtime config — Claude model tiers, speakers, protocols |
| 4 | voice-agent/ha_client.py | Shared HA REST client (new) |
| 5 | voice-agent/webhook_dispatcher.py | HTTP server receiving HA callbacks |
| 6 | voice-agent/security.py | Voice PIN, blocked/sensitive action lists |
| 7 | home-assistant/configuration.yaml | HA root config — input_booleans, groups, rest_command |
| 8 | dashboard/src/app/page.tsx | Main dashboard page — all views |
| 9 | dashboard/src/middleware.ts | Auth, rate limiting, security headers |
| 10 | dashboard/src/app/api/health/route.ts | System health endpoint |

---

## Standards

- Python: Type hints on all functions, logging (never print), no bare except
- YAML: Every automation needs alias, description, trigger, condition, action. All device actions need continue_on_error: true
- Paths: /config/aura/ on Pi, never /home/pi/aura/
- Secrets: Never in code, always from .env via os.environ
- The system runs on Raspberry Pi 5 with Home Assistant OS (Alpine Linux). Package manager is apk, not apt-get.

---

## Expected Output

For each issue found:
1. File path and line number
2. Severity (Critical / High / Medium / Low)
3. Description of the bug
4. Recommended fix
5. Whether it blocks hardware deployment (yes/no)

Be adversarial. Try to break things. Focus on runtime crashes, security bypasses, and data flow failures. This controls physical door locks and cameras — it must be bulletproof.
