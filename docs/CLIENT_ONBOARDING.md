# AURA Client Onboarding — Internal Operations Guide

This document covers the end-to-end process for deploying AURA at a client's home. It is written for OASIS AI staff doing the installation.

---

## Pre-Visit Checklist

Complete everything on this list before leaving for the client's location. Showing up without hardware or without key information costs everyone time.

### Hardware
- [ ] Raspberry Pi 5 (8GB) — pre-loaded with Home Assistant OS on a freshly flashed microSD
- [ ] Pi 5 power supply (27W USB-C official)
- [ ] Ethernet cable (2m minimum)
- [ ] USB microphone
- [ ] All devices included in the client's package (see their invoice)
- [ ] Spare microSD card in case of flashing issues
- [ ] USB-A hub (some Pi setups need one)
- [ ] Laptop with this repo cloned and scripts ready

### Client Information (gather before visit)
- Home WiFi network name and password
- Router admin access (needed to set a static IP reservation for the Pi)
- Which rooms they want covered and approximate LED strip lengths
- Existing smart devices they want connected (model numbers help)
- Spotify or Apple Music preference
- Any schedule preferences (morning routine time, sleep time)
- Their phone OS (iPhone vs Android) for presence detection setup

### Accounts to Prepare
- Create a `clients/{client_name}/` directory from the template (see below)
- Have the Govee API key process ready (they will need to apply from their own Govee account)
- Generate a Spotify developer app if they want Spotify integration

---

## On-Site Setup

Work through these steps in order. The full process takes 2–4 hours depending on package tier and client participation.

### 1. Network Setup
- Connect the Pi to the client's router via ethernet
- Locate the Pi's IP address from the router admin panel
- Set a static DHCP reservation for the Pi (so its IP never changes)
- Confirm you can reach `http://<pi-ip>:8123` from your laptop on the same network

### 2. Flash and Boot Home Assistant
If the Pi is not already flashed, do it now using Balena Etcher and the latest HA OS image. See SETUP_GUIDE.md Step 1 for the full procedure.

### 3. Create the HA Owner Account
Use the client's name and an email address they control. Walk them through creating a password and make sure they store it in a password manager. This is their system — they own the credentials.

### 4. Set Location and Timezone
Accurate location enables sunrise/sunset automations and local weather. Set it to the client's city and confirm the timezone.

### 5. Install Add-ons
Install SSH & Web Terminal and ha-mcp following SETUP_GUIDE.md Step 3. Set the SSH password, toggle "Start on boot" for both add-ons.

### 6. Generate Access Token
Generate a long-lived access token under the client's HA account (SETUP_GUIDE.md Step 4). Store it in the client's `.env` file in the repo, never in a plain document.

### 7. Add All Smart Devices
Set up each device physically first (plug it in, pair it with its native app, confirm it works from the app). Then add the HA integration. Integrations to add per package:

- **All packages:** Govee, TP-Link Kasa
- **Standard and above:** Sonos, Spotify, SwitchBot
- **Pro:** August Smart Lock, Wyze Cam, Roborock, Ecobee

Rename every entity to match the AURA naming convention:
`light.{room}_leds`, `switch.{room}_plug`, `media_player.sonos_{room}`

### 8. Deploy Client-Specific Config
```bash
./scripts/deploy/deploy_client.sh {client_name}
```

This uses the overrides in `clients/{client_name}/config_overrides.yaml` to customize scene colours, entity IDs, and enabled features for this client's specific setup.

### 9. Deploy Automations
```bash
./scripts/deploy/update_configs.sh
```

Reload automations in HA and verify none show errors.

### 10. Set Up Clap Detection
Run `./scripts/setup/pi_setup.sh` on the Pi. Physically place the USB microphone in the primary living space (central location, away from the TV speakers). Test detection using `journalctl -u clap_service -f` while clapping.

Calibrate the threshold in `clap-trigger/config.yaml` until it reliably detects intentional claps without false triggers.

---

## Client-Specific Configuration

Every client gets their own directory:

```bash
cp -r clients/.template/ clients/{client_name}/
```

Edit `clients/{client_name}/config_overrides.yaml` to reflect:
- Their device entity IDs
- Which scenes are enabled for their package tier
- Any custom room names or device models
- Their preferred clap patterns

Do not modify any base config files. All client customization lives in the `clients/` directory.

---

## Client Handoff

Allow 30–45 minutes at the end of the visit for the handoff. The client should be hands-on during this part.

### Demo Each Scene
Trigger every scene manually from the HA dashboard while the client watches. Explain what each one does and when they would use it:
- Welcome Home — arriving at the apartment
- Goodnight — going to bed
- Morning Routine — automated, fires at their chosen time
- Studio / Focus — for work or content creation
- Movie Mode — for watching films
- Party Mode — for having people over

### Explain Clap Patterns
Make sure the client can reliably trigger each clap pattern before you leave:
- Double clap — Welcome Home / room toggle
- Triple clap — Studio Mode
- Quad clap — Party Mode

Have them practice each one while watching the lights respond.

### Walk Through the Dashboard
Show them the HA Lovelace dashboard on any browser or the HA companion app on their phone. Point out:
- How to manually override any light or device
- How to check automation history
- How to mute or disable automations temporarily (useful when they don't want clap detection active)

### Provide Support Information
Give the client the OASIS AI support contact. If they are on the AURA Care plan, explain the monthly check-in cadence and how to request a new scene or automation.

Leave them with:
- The HA URL and their login credentials (in a password manager, not on paper)
- A brief one-page cheat sheet of clap patterns and scene names (customize the template in `docs/`)
- The support contact and response time expectations

---

## Post-Visit

- Commit any client-specific config changes to the repo under `clients/{client_name}/`
- Log the installation date and device inventory in the client record
- Schedule the first AURA Care check-in if applicable (30 days after install)
- Note any outstanding items (devices on backorder, features pending Phase 4, etc.)
