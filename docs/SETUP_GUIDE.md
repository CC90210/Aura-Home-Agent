# AURA Setup Guide — Zero to Working System

This guide walks you through a complete AURA installation from scratch. It assumes you are technical but unfamiliar with embedded Linux, Home Assistant, or smart home ecosystems. Every step is spelled out. Do not skip sections — each one builds on the last.

Estimated total time: 3–5 hours for a first installation.

> **Quick Start**: For the impatient, run `bash scripts/setup/wizard.sh` on your desktop to auto-generate your `.env` file and test connectivity. Then skip to Step 6. The wizard handles Steps 4–5 interactively.

---

## Prerequisites

Before you start, have the following on hand:

### Hardware
- Raspberry Pi 5 (8GB RAM recommended)
- microSD card, 32GB minimum (Class 10 / A2 rated — SanDisk Extreme or Samsung Pro Endurance)
- microSD card reader for your desktop/laptop
- Ethernet cable (the Pi must be wired during initial setup — WiFi comes later if desired)
- USB-A to USB-C cable and Pi 5 power supply (27W USB-C, official Pi supply preferred)
- USB microphone (any basic USB mic works — $10–30 range is fine)
- Smart devices (Govee LED strips, TP-Link Kasa plugs, Sonos speakers — see PRODUCT_LIST.md)

### Software (on your desktop)
- Balena Etcher: https://etcher.balena.io — for flashing the SD card
- A terminal (Terminal on Mac, WSL or Git Bash on Windows, any shell on Linux)
- Git
- A text editor (VS Code recommended)

### Accounts
- Govee account + API key (Govee Home app → Profile → About → Apply for API Key)
- Spotify developer account if using music integration (developer.spotify.com)

---

## Step 1: Flash Home Assistant OS

Home Assistant OS is a purpose-built Linux distribution. It is not a regular Linux install — do not try to install it manually. Use the official image and Balena Etcher.

**1.1** Go to https://www.home-assistant.io/installation/raspberrypi and download the latest Home Assistant OS image for Raspberry Pi 5. The file will be named something like `haos_rpi5-64-XX.X.img.xz`. Do not extract it — Etcher handles compressed images directly.

**1.2** Insert your microSD card into your desktop's card reader.

**1.3** Open Balena Etcher. Click "Flash from file" and select the `.img.xz` file you downloaded. Click "Select target" and choose your microSD card. Double-check you have the right drive — this will erase everything on it. Click "Flash" and wait for it to finish (5–10 minutes).

**1.4** Once Etcher says the flash is complete and verified, eject the microSD card safely.

**1.5** Insert the microSD card into the Raspberry Pi 5 (slot is on the underside of the board).

**1.6** Plug the ethernet cable into the Pi and your router. Then plug in the power supply. The Pi will boot automatically.

**1.7** Wait 5–10 minutes on first boot. Home Assistant needs to download and configure itself. The LED on the Pi board will go from a flashing pattern to a steady green when it is ready.

---

## Step 2: Initial Home Assistant Setup

**2.1** On any device connected to the same network as the Pi, open a browser and go to:

```
http://homeassistant.local:8123
```

If that does not load after 10 minutes, this is usually an mDNS issue. Windows users: if `homeassistant.local` does not load, you may need to find the Pi's IP address directly. Log into your router's admin page (usually http://192.168.1.1 — check the label on your router if you are unsure) and look for a device named "homeassistant" in the connected devices list. Use that IP address instead, for example: `http://192.168.1.100:8123`. You can use this IP address anywhere in this guide in place of `homeassistant.local`.

**2.2** You will see the Home Assistant onboarding screen. Click "Create my smart home."

**2.3** Create your owner account. This is the main admin account — use a strong password and store it somewhere safe. Fill in:
- Name (e.g., CC)
- Username (e.g., `cc`)
- Password

**2.4** On the next screen, set your home's name, location, timezone, unit system (metric for Canada), and currency. This is used for automations that depend on sunrise/sunset times and local weather.

**2.5** Home Assistant will offer to automatically detect devices on your network. You can skip this for now — we will add devices intentionally in Step 7.

**2.6** You are now inside the Home Assistant dashboard. Bookmark `http://homeassistant.local:8123`.

---

## Step 3: Install Add-ons

Add-ons are optional software packages that run alongside Home Assistant on the Pi. You need two: SSH access and the MCP server for Claude Code.

**3.1 Install Advanced SSH & Web Terminal**

- In the left sidebar, click "Settings"
- Click "Add-ons"
- Click "Add-on Store" (bottom right)
- Search for "Advanced SSH & Web Terminal" (published by the Home Assistant community — make sure it says "Advanced" in the name)
- Click it and click "Install" — wait for it to finish
- After installation, click the "Configuration" tab and set a password for the root user. Save it.
- Still on the Configuration tab, find the "Protection mode" toggle and turn it OFF. This is required for AURA's setup script to work correctly — the script needs to interact with the underlying OS in ways that Protection mode blocks. Click Save.
- Click "Start", then toggle "Start on boot" to on
- Click "Show in sidebar" so you can easily access the terminal from the HA web UI

**3.2 Install ha-mcp (AI Bridge)**

- Still in the Add-on Store, click the three-dot menu in the top-right corner and select "Repositories"
- Add this repository URL: `https://github.com/homeassistant-ai/ha-mcp`
- Click "Add" then close the dialog
- Search for "ha-mcp" in the Add-on Store (it may take a moment to appear)
- Click it and click "Install"
- After installation, click "Start" and toggle "Start on boot" to on

If ha-mcp does not appear in the store after adding the repository, try refreshing the page and waiting a minute.

---

## Step 4: Generate a Long-Lived Access Token

Claude Code and scripts authenticate to Home Assistant using a long-lived access token. This is equivalent to a password — treat it like one.

**4.1** Click your profile icon in the bottom left of the Home Assistant sidebar (your username initials).

**4.2** Scroll down to the "Security" section. Under "Long-lived access tokens," click "Create token."

**4.3** Give it a name like `aura-claude-code`. Click "OK."

**4.4** Copy the token immediately — it will only be shown once. Paste it into a secure note (password manager, not a plain text file).

You will use this token in the `.env` file in the next step.

---

## Step 5: Clone the AURA Repo on the Pi

Home Assistant OS is built on Alpine Linux. This is a minimal embedded Linux — it is not Ubuntu or Raspberry Pi OS, and many tools you might expect are not pre-installed. In particular, `git` is not installed by default. You will install it using `apk`, which is Alpine's package manager.

**5.1** Open the "Advanced SSH & Web Terminal" from the HA sidebar (or SSH in from your desktop terminal):

```bash
ssh root@homeassistant.local
```

Enter the password you set in Step 3.1 when prompted.

**5.2** Install git using Alpine's package manager:

```bash
apk add git
```

This will take a few seconds. You only need to do this once.

**5.3** Navigate to the Home Assistant config directory:

```bash
cd /config
```

**5.4** Clone the AURA repository into `/config/aura/`:

```bash
git clone https://github.com/YOUR_ORG/aura.git aura
```

Replace `YOUR_ORG/aura` with the actual repository path. If the repo is private, you will need to authenticate with a GitHub personal access token.

**5.5** Move into the cloned directory and copy the environment template:

```bash
cd /config/aura
cp .env.example .env
```

**5.6** Open `.env` in the terminal editor:

```bash
nano .env
```

Fill in every variable. The critical ones are:

```
HA_URL=http://homeassistant.local:8123
HA_TOKEN=<the long-lived access token from Step 4>
GOVEE_API_KEY=<your Govee API key>
SPOTIFY_CLIENT_ID=<from developer.spotify.com>
SPOTIFY_CLIENT_SECRET=<from developer.spotify.com>
```

Save with Ctrl+O, Enter, then exit with Ctrl+X.

**5.7** Secure the .env file so only root can read it:

```bash
chmod 600 /config/aura/.env
```

---

## Step 6: Run the Pi Setup Script

The setup script installs Python dependencies, creates the clap detection virtual environment, registers the clap detection systemd service, and sets correct permissions. The script uses `apk` (Alpine's package manager) — this is correct for Home Assistant OS and is not a mistake.

**6.1** Make the script executable and run it:

```bash
cd /config/aura
chmod +x scripts/setup/pi_setup.sh
./scripts/setup/pi_setup.sh
```

The script will print progress messages. If anything fails, read the error message — it will usually tell you exactly what is missing.

**6.2** After the script completes, verify the clap detection service is running:

```bash
systemctl status clap_service
```

You should see "active (running)". If it shows "failed," check Step 8 in TROUBLESHOOTING.md.

---

## Step 7: Add Smart Devices to Home Assistant

Now you connect your actual smart devices. Home Assistant handles this through Integrations.

**7.1 Govee LED Strips**

- In HA, go to Settings → Devices & Services → Add Integration
- Search for "Govee" and select it
- Enter your Govee API key when prompted
- Home Assistant will discover all Govee devices linked to your account and create entities for them
- Important: For LAN control (faster, no rate limits), you must also enable LAN Control per device in the Govee app: open the device, go to Settings → LAN Control → Enable. Do this for every Govee device.

**7.2 TP-Link Kasa Smart Plugs**

- Go to Settings → Devices & Services → Add Integration
- Search for "TP-Link Kasa" and select it
- HA will scan your local network and find Kasa plugs automatically
- Confirm the devices listed and click Submit

**7.3 Sonos Speakers**

- Go to Settings → Devices & Services → Add Integration
- Search for "Sonos" and select it
- HA will discover Sonos speakers on the network automatically
- If no speakers are found, check that the Sonos and Pi are on the same network segment (see TROUBLESHOOTING.md)

**7.4 Spotify**

- Go to Settings → Devices & Services → Add Integration
- Search for "Spotify" and select it
- Follow the OAuth flow — you will be redirected to Spotify to authorize the connection
- After authorization, HA creates a `media_player.spotify_*` entity

**7.5 Verify Entity IDs**

After adding devices, verify their entity IDs match what the AURA automations expect. Go to Settings → Devices & Services → Entities and search for your devices. Common expected IDs:

- `light.living_room_leds`
- `light.bedroom_leds`
- `switch.living_room_plug`
- `media_player.living_room_speaker`

If the auto-generated IDs differ, either rename them in HA (click the entity, click the gear icon, edit the entity ID) or update the automation YAML files to match. Renaming in HA is cleaner.

---

## Step 8: Connect Claude Code via MCP

This step is done on your desktop, not the Pi.

**8.1** Make sure Claude Code is installed on your desktop. If not, install it via the Anti-Gravity IDE or follow the Claude Code installation instructions at https://claude.ai/code.

**8.2** Make sure Docker Desktop is installed on your desktop and that it is actually running — the Docker icon should be visible in your taskbar/menu bar and showing a "running" status. If Docker is installed but not started, the MCP connection will fail with a connection error. Start Docker Desktop before continuing.

**8.3** In your terminal on your desktop, run:

```bash
claude mcp add ha-mcp -- docker run -i --rm \
  -e HA_URL=http://homeassistant.local:8123 \
  -e HA_TOKEN=<your long-lived access token> \
  voska/hass-mcp
```

Replace `<your long-lived access token>` with the token from Step 4. This registers ha-mcp as an MCP server in Claude Code. If you do not have Docker, install it from https://docker.com.

**8.4** Test the connection by opening Claude Code and asking: "What lights are available in Home Assistant?" If Claude Code returns a list of your devices, the MCP connection is working.

**8.5** If you prefer not to use Docker, you can connect to the ha-mcp add-on running directly on the Pi. In that case, get the add-on's port from its configuration in HA and point the MCP URL at the Pi's IP address directly. Refer to the ha-mcp documentation for the exact connection string.

---

## Step 9: Deploy Automations

The AURA automation YAML files need to be copied into the Home Assistant config directory so HA can load them. This includes `configuration.yaml`, which defines the input boolean helpers used for mode tracking — you do not need to create those manually.

**9.1** From your desktop, run the full deployment script (deploys YAML configs + Python services):

```bash
cd /path/to/your/local/aura/repo
bash scripts/deploy/full_deploy.sh --restart --env --pip
```

This validates YAML, deploys configs via SCP, deploys Python services, optionally installs pip dependencies, and restarts HA + systemd services. For configs only, use `bash scripts/deploy/update_configs.sh --restart`.

**9.2** After the script completes, restart Home Assistant so it picks up all the new configuration including `configuration.yaml`. In the HA web UI: Settings → System → Restart. Wait for HA to come back up (about 60 seconds) before continuing.

**9.3** If the deploy script is not yet written (early installation), you can manually copy files:

```bash
scp home-assistant/configuration.yaml root@homeassistant.local:/config/configuration.yaml
scp -r home-assistant/automations/* root@homeassistant.local:/config/automations/
scp -r home-assistant/scenes/* root@homeassistant.local:/config/scenes/
```

Then restart HA: Settings → System → Restart.

**9.4** Verify automations loaded without errors: Settings → Automations & Scenes. All six core automations should appear. If any show a red error badge, click them to read the error — it is usually a missing entity ID.

---

## Step 10: Test Everything

Run through these tests in order. Do not skip one and assume it works.

**10.1 Run the verification script**

```bash
ssh root@homeassistant.local
cd /config/aura
./scripts/setup/verify_install.sh
```

This checks Python dependencies, service status, .env completeness, and HA API reachability. Fix anything it flags before continuing.

**10.2 Test webhooks manually**

From your desktop terminal, fire each webhook and observe whether the corresponding scene triggers on your devices:

```bash
# Double clap — should trigger Welcome Home scene
curl -X POST http://homeassistant.local:8123/api/webhook/aura_double_clap

# Triple clap — should trigger Studio Mode
curl -X POST http://homeassistant.local:8123/api/webhook/aura_triple_clap

# Quad clap — should trigger Party Mode
curl -X POST http://homeassistant.local:8123/api/webhook/aura_quad_clap
```

If a webhook fires but nothing happens, check Settings → Automations & Scenes and confirm the relevant automation is enabled.

If a webhook returns a 404, the automation using that webhook ID is not loaded or the webhook ID in the automation YAML does not match.

**10.3 Test clap detection**

Stand near the USB microphone and clap twice in quick succession. The Living Room lights should change. If nothing happens:

1. Check the service is running: `systemctl status clap_service`
2. Watch the live log: `journalctl -u clap_service -f`
3. Clap again and watch the log for "clap detected" or "pattern matched" messages
4. If claps are detected but the webhook does not fire, the HA_URL or HA_TOKEN in `.env` may be wrong

Adjust the sensitivity threshold in `clap-trigger/config.yaml` if the detection is too sensitive (false triggers from normal noise) or not sensitive enough (missing actual claps). See TROUBLESHOOTING.md for guidance.

**10.4 Test Claude Code control**

Open Claude Code on your desktop and try:

- "Turn on the living room lights and set them to warm amber"
- "Play a chill playlist on the Sonos"
- "Activate studio mode"

If these work, the full stack is operational.

---

## Step 11: Input Boolean Helpers for Mode Tracking

AURA uses `input_boolean` helpers in Home Assistant to track active modes (gaming, streaming, etc.). Automations read these booleans to know which scene is currently active and to prevent conflicting automations from firing simultaneously.

The input boolean helpers are automatically defined in `configuration.yaml` and will appear in Home Assistant after you deploy the configs and restart (which you did in Step 9). You do not need to create them manually.

To verify they are present, go to Settings → Devices & Services → Entities and search for `input_boolean`. You should see all of the following:

| Entity ID | Purpose |
|---|---|
| `input_boolean.gaming_mode_active` | Tracks gaming scene state |
| `input_boolean.streaming_mode_active` | Tracks content creation/streaming scene |
| `input_boolean.focus_mode_active` | Tracks deep work / focus scene |
| `input_boolean.movie_mode_active` | Tracks movie scene state |
| `input_boolean.party_mode_active` | Tracks party scene state |
| `input_boolean.guest_mode_active` | Enables guest-appropriate automations |
| `input_boolean.sleep_mode_active` | Suppresses all non-alarm automations overnight |

If any are missing, check that `configuration.yaml` was deployed correctly and that HA was fully restarted after the deploy.

---

## Step 12: Set Up Person Entities for Conaugh and Adon

Presence detection (knowing who is home) requires person entities linked to the HA Companion app on each person's iPhone.

**12.1 Install the HA Companion App**

Both Conaugh and Adon need to install the Home Assistant Companion app on their iPhones:
- App Store: search "Home Assistant" — the official app by Nabu Casa
- Open the app and tap "Connect to server"
- Enter `http://homeassistant.local:8123` (or the Pi's IP if `.local` does not resolve)
- Log in with their respective HA user account

**12.2 Create User Accounts for Conaugh and Adon**

Each person needs their own HA user account so the Companion app can authenticate separately.

- In HA, go to Settings → People → Add Person
- Create a person for Conaugh: name "Conaugh", create a new user account linked to this person
- Create a person for Adon: name "Adon", create a new user account linked to this person
- Set appropriate permissions — the default "User" role is sufficient (not Administrator)

**12.3 Link the Companion App to Each Person**

Once each person logs into the Companion app with their account, HA will automatically create a `device_tracker` entity for their phone. To link it to the person entity:

- In HA, go to Settings → People
- Click on Conaugh → click "Add device tracker" → select Conaugh's iPhone tracker entity
- Click on Adon → click "Add device tracker" → select Adon's iPhone tracker entity

HA will now expose `person.conaugh` and `person.adon` entities with states `home` or `not_home`.

**12.4 Enable Location Permissions on iPhone**

For presence detection to work, the Companion app needs "Always" location access:
- iPhone Settings → Privacy & Security → Location Services → Home Assistant → select "Always"
- Also enable "Precise Location"

**12.5 Test Presence Detection**

Ask each person to leave the apartment network and return. After a brief delay (30–60 seconds), their person entity state should flip between `home` and `not_home`. You can watch this live in HA: Developer Tools → States → search for `person.`.

If presence is not updating, see TROUBLESHOOTING.md — Person Not Detected Correctly.

---

## Step 13: Set Up the Voice Agent

The voice agent runs on the Pi, listens for a wake word ("Hey Aura"), transcribes speech using faster-whisper (local — no cloud STT needed), sends the transcript to the Claude API for intent processing, and speaks the response back through the speakers using ElevenLabs TTS.

**13.1 Install Voice Agent Dependencies**

SSH into the Pi and install the requirements. The voice agent uses a virtual environment located at `/config/aura/.venv/`:

```bash
ssh root@homeassistant.local
cd /config/aura
python -m venv .venv
.venv/bin/pip install -r voice-agent/requirements.txt
```

The requirements include `faster-whisper`, `openWakeWord`, `anthropic`, `elevenlabs`, and `pydub`. The `faster-whisper` package will download its model files on first run — this takes a few minutes and requires internet access on the Pi.

You also need ffmpeg for audio format conversion (used by pydub). Because Home Assistant OS uses Alpine Linux, install it with `apk`:

```bash
apk add ffmpeg
```

**13.2 Configure ElevenLabs Voice**

In your `.env` file on the Pi, ensure these are set:

```
ELEVENLABS_API_KEY=<your key from elevenlabs.io>
ELEVENLABS_VOICE_ID=<the voice ID you want AURA to use>
```

To find a voice ID: log into elevenlabs.io → Voices → click a voice → the ID is shown in the URL or voice details panel. The default AURA voice should be something calm and clear — avoid overly dramatic voices for a smart home context.

**13.3 Test the Voice Agent**

Before running the full agent, run it in test mode to confirm the wake word engine, microphone, and audio output are all working:

```bash
cd /config/aura/voice-agent
/config/aura/.venv/bin/python aura_voice.py --test
```

Speak "Hey Aura" toward the USB microphone. The test mode will check wake word detection and play a short TTS phrase through the speakers. If wake word detection does not trigger, see TROUBLESHOOTING.md — Wake Word Not Detecting. If no audio plays, see TROUBLESHOOTING.md — TTS Not Speaking.

**13.4 Run the Full Voice Agent**

```bash
cd /config/aura/voice-agent
/config/aura/.venv/bin/python aura_voice.py
```

Say "Hey Aura" and then speak a command (for example: "Turn on studio mode"). The agent should:
1. Detect the wake word and play a brief chime
2. Transcribe your command
3. Send it to Claude for intent processing
4. Execute the resulting HA action
5. Speak a confirmation response back through the speakers

**13.5 Register as a Systemd Service**

To have the voice agent start automatically on Pi boot:

```bash
cp /config/aura/voice-agent/aura_voice.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable aura_voice
systemctl start aura_voice
systemctl status aura_voice
```

You should see "active (running)."

**USB Microphone Sharing**: Both the clap detector and voice agent need the microphone. If you have ONE USB mic, you need to configure ALSA to share it:

1. SSH into the Pi terminal and find the ALSA card and device numbers for your USB mic:

```bash
arecord -l
```

Look for a line like `card 1: Device [USB Audio Device], device 0:`. The numbers after `card` and `device` are your hardware address — in this example `hw:1,0`. Substitute your own numbers in the config block below.

2. Create the dsnoop shared capture device using the correct hardware address:

```bash
cat >> /etc/asound.conf << 'EOF'
pcm.dsnoop_mic {
    type dsnoop
    ipc_key 1234
    slave {
        pcm "hw:1,0"   # Replace 1,0 with your card,device numbers from arecord -l
        channels 1
        rate 16000
    }
}
EOF
```

3. Set `input_device_name: dsnoop_mic` in both `voice-agent/config.yaml` and `clap-trigger/config.yaml` so both services use the shared virtual device instead of the raw hardware device.

4. Restart both services:

```bash
systemctl restart clap_service
systemctl restart aura_voice
```

Alternatively, use TWO USB mics — one for clap detection, one for voice. Plug both into the Pi and set each `input_device_index` to the corresponding PyAudio device index:

```bash
/config/aura/.venv/bin/python -c "import pyaudio; p = pyaudio.PyAudio(); [print(i, p.get_device_info_by_index(i)['name']) for i in range(p.get_device_count())]"
```

---

## Step 14: Set Up the Adaptive Learning System

The adaptive learning system observes how you interact with AURA over time — which scenes you activate at which times, what adjustments you make after activating a scene, and how long you stay in each mode. It stores this data in a local SQLite database on the Pi and uses it to suggest and eventually automate personalizations.

The learning engine is triggered by Home Assistant webhooks and runs within the voice agent process — it does not run as a separate standalone service.

**14.1 Verify the Learning Directory Exists**

```bash
ls /config/aura/learning/
```

You should see `pattern_engine.py`, `habit_tracker.py`, and `requirements.txt`. If the directory is missing, pull the latest repo changes:

```bash
cd /config/aura && git pull
```

**14.2 Install Learning System Dependencies**

```bash
/config/aura/.venv/bin/pip install -r /config/aura/learning/requirements.txt
```

The dependencies are lightweight — primarily data processing libraries. `sqlite3` is part of Python's standard library and does not need to be installed separately.

**14.3 Configure the Database Path**

In your `.env` file, confirm:

```
AURA_DB_PATH=/config/aura/data/patterns.db
AURA_VOICE_PIN=<a non-obvious 4-6 digit PIN>
```

This path is relative to `/config/aura/`. The learning engine will create the SQLite file automatically on first run — you do not need to create it manually.

**14.4 Verify Data Is Being Written**

After using AURA normally for a day (activating scenes, adjusting lights), check that the learning database is accumulating records. If you need the `sqlite3` command-line tool to inspect the database, install it first:

```bash
apk add sqlite
```

Then query the database:

```bash
sqlite3 /config/aura/data/patterns.db "SELECT COUNT(*) FROM events;"
```

A non-zero count confirms events are being logged. If the count stays at zero, check that the voice agent is running and that HA webhooks are configured correctly. See TROUBLESHOOTING.md — Pattern Learning Not Working.

---

## Step 15: Set Up the Web Dashboard

The AURA web dashboard is a Next.js application that provides a mobile-first UI for controlling scenes, viewing device states, and reviewing learning insights. It can be run locally on your desktop or deployed to Vercel.

**15.1 Install Node.js Dependencies**

On your desktop (not the Pi — the dashboard runs on your desktop or a hosted server):

```bash
cd /path/to/your/local/aura/repo/dashboard
npm install
```

**15.2 Configure Environment Variables**

Copy the dashboard environment template:

```bash
cp .env.example .env.local
```

Open `.env.local` and fill in:

```
NEXT_PUBLIC_HA_URL=http://homeassistant.local:8123
HA_TOKEN=<your long-lived access token from Step 4>
```

Only `NEXT_PUBLIC_HA_URL` should be public. Keep `HA_TOKEN` server-side in the dashboard environment so it never ships to the browser bundle.

**15.3 Run Locally**

```bash
npm run dev
```

Open your browser at `http://localhost:3000`. You should see the AURA dashboard with live device states pulled from Home Assistant. If the dashboard loads but shows no devices or connection errors, see TROUBLESHOOTING.md — Dashboard Won't Connect to HA.

**15.4 Build and Verify**

Before deploying, verify the production build has zero errors:

```bash
npm run build
```

Fix any TypeScript or lint errors before proceeding.

**15.5 Deploy to Vercel (Optional)**

If you want the dashboard accessible from outside your home network (or from any device without running `npm run dev`):

```bash
npm install -g vercel
vercel
```

Follow the prompts. When Vercel asks for environment variables, add `NEXT_PUBLIC_HA_URL`, `HA_TOKEN`, and `DASHBOARD_AUTH_TOKEN`. Note: for Vercel to reach your Home Assistant instance, your Pi must be accessible from the internet — either via Nabu Casa cloud (the official HA remote access service at nabu.casa) or through a VPN/tunnel. The simplest path is Nabu Casa: Settings → Home Assistant Cloud → sign up, then use the `https://your-instance.ui.nabu.casa` URL as `NEXT_PUBLIC_HA_URL`.

---

## You Are Done

At this point you have a fully operational AURA installation:
- Home Assistant running on the Pi, controlling all smart devices
- Input boolean helpers deployed via `configuration.yaml` and active after restart
- Person entities configured for Conaugh and Adon with presence detection
- Clap detection active and wired to scene webhooks
- Voice agent running with wake word, STT, Claude intent processing, and ElevenLabs TTS
- Adaptive learning system recording usage patterns and building personalization data
- Web dashboard deployed and connected to Home Assistant
- Claude Code connected via MCP and able to control everything by natural language
- All automations deployed and tested

For adding more devices, creating new scenes, or building custom automations, use Claude Code directly — it can create and modify automations by talking to Home Assistant through the MCP connection.

For issues, see TROUBLESHOOTING.md.
