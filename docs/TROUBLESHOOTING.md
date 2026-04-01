# AURA Troubleshooting Guide

Work through the relevant section below. Each issue lists the most common causes first. If you exhaust all steps and the problem persists, check the Home Assistant community forums or open an issue in the AURA repo with the full log output attached.

---

## Home Assistant Not Reachable at homeassistant.local:8123

**Symptoms:** Browser says "This site can't be reached" or times out. The address `homeassistant.local` does not resolve.

**Cause 1: The Pi is still booting.**
First boot takes 5–10 minutes because HA downloads its own container images. Wait the full time and try again before troubleshooting anything else.

**Cause 2: mDNS is not working on Windows.**
Windows does not always resolve `.local` hostnames by default, especially on corporate-managed machines or when certain antivirus or firewall software is running.

Fix: Find the Pi's IP address from your router's admin panel (usually at `192.168.1.1` or `192.168.0.1` — log in and look at the DHCP client list for a device named "homeassistant"). Then access HA directly by IP:

```
http://192.168.1.XXX:8123
```

Replace `XXX` with the actual last octet. You can also set a static IP reservation in your router so the Pi always gets the same address.

**Cause 3: Pi is not connected to the network.**
Confirm the ethernet cable is fully seated at both ends. The ethernet port on the Pi should show an amber link light and a green activity light. If not, try a different cable or a different port on your router.

**Cause 4: SD card not properly flashed.**
If the Pi's LED pattern does not settle into a steady green after 10 minutes, it may have failed to boot. Reflash the SD card using Balena Etcher, making sure to download a fresh image from home-assistant.io.

---

## Clap Detection Too Sensitive or Not Sensitive Enough

**Symptoms:** The system triggers on background noise (speech, music, door closing) or does not detect actual claps.

Open `clap-trigger/config.yaml` on the Pi:

```bash
nano /config/aura/clap-trigger/config.yaml
```

Find the `threshold` parameter. It is an amplitude value — higher means less sensitive, lower means more sensitive.

**Too sensitive (false triggers):** Increase the threshold. Try incrementing by 500–1000 at a time and re-testing.

**Not detecting claps:** Decrease the threshold. Try decrementing by 500–1000 at a time.

After changing the config, restart the service:

```bash
systemctl restart clap_service
```

Watch the live log while testing:

```bash
journalctl -u clap_service -f
```

You should see amplitude values logged on each audio spike. Use those numbers to calibrate — your claps should be well above the threshold; background noise should be well below it.

**Also check:** `pattern_timeout` — this is the maximum time in seconds between individual claps in a pattern. If your clapping pace is slower than this value allows, the pattern will not be recognized. Try increasing it to 1.5–2.0 seconds.

---

## Webhook Not Firing

**Symptoms:** You curl the webhook URL and get a 404, or the automation does not trigger even though the curl command returns 200.

**Step 1: Confirm the automation is enabled.**
In HA: Settings → Automations & Scenes. Find the automation. If it has a toggle, make sure it is on.

**Step 2: Verify the webhook ID.**
The webhook ID in the curl command must exactly match the `webhook_id` in the automation YAML — case-sensitive, no extra spaces. Check `home-assistant/automations/double_clap_toggle.yaml` and compare to what you are curling.

**Step 3: Check HA logs.**
Settings → System → Logs. Look for errors around the time you fired the webhook. HA will usually log a message when a webhook is received, and it will also log if an automation action failed.

**Step 4: Test with a direct service call instead.**
In HA, go to Developer Tools → Services. Select `automation.trigger` and enter the automation entity ID. If the scene triggers this way but not via webhook, the issue is in the webhook ID or the automation trigger configuration — not the scene itself.

**Step 5: Reload automations.**
Sometimes HA does not pick up YAML changes until you reload. In HA: Settings → Automations & Scenes → click the reload button (circular arrow, top right). Then test again.

---

## MCP Connection Failed

**Symptoms:** Claude Code cannot reach Home Assistant. Error messages like "MCP server failed to connect," "connection refused," or "unauthorized."

**Cause 1: Wrong HA_URL.**
The URL must be reachable from the machine running Docker (your desktop). If `homeassistant.local` does not resolve on your desktop, use the Pi's IP address instead:

```
HA_URL=http://192.168.1.XXX:8123
```

**Cause 2: Wrong or expired HA_TOKEN.**
Long-lived tokens do not expire, but they can be revoked. Go to your HA profile → Security → Long-lived access tokens. If the token you copied is not listed, it was revoked and you need to create a new one.

**Cause 3: Docker is not running.**
The MCP command uses Docker to run the `voska/hass-mcp` container. Run `docker ps` in your terminal — if Docker is not running, start it.

**Cause 4: ha-mcp add-on is not running on the Pi.**
SSH into the Pi and check: Settings → Add-ons → ha-mcp. The status should be "Running." If it shows "Stopped," click Start.

**Cause 5: Port blocked by firewall.**
Port 8123 must be reachable from your desktop to the Pi over your local network. Temporarily disable any desktop firewall software and test again. If that fixes it, add an exception for port 8123 to the firewall rules.

---

## Govee Lights Not Responding

**Symptoms:** HA shows the Govee entities but sending commands has no effect, or HA shows them as "unavailable."

**Cause 1: API key is wrong or not activated.**
Check that the API key in your `.env` and in the HA Govee integration matches what is in your Govee account (Govee Home app → Profile → About). API keys are emailed after approval — make sure you are using the correct email.

**Cause 2: LAN Control is not enabled on the device.**
The Govee integration defaults to cloud API, but for reliable control you need LAN enabled. In the Govee Home app: open each device → Settings (gear icon) → LAN Control → toggle on. Do this for every device individually.

**Cause 3: Rate limit exceeded.**
The Govee cloud API allows 100 requests per minute per key. If you are sending many commands in quick succession (e.g., a music-reactive scene), you may hit this limit. Symptoms: some commands work, others are silently dropped. Solution: use LAN Control instead, which has no rate limits.

**Cause 4: Device is offline or unreachable.**
Open the Govee Home app on your phone and check if the device is online and controllable from the app. If the app cannot control it either, the device itself has an issue (power, WiFi connectivity, firmware). Reboot the device and try again.

**Cause 5: HA integration needs re-authentication.**
Occasionally the Govee integration token expires. Go to Settings → Devices & Services → Govee → click the three-dot menu → Reload (or Delete and re-add).

---

## Sonos Not Discovered

**Symptoms:** HA Sonos integration says "No devices found" or a speaker that was working disappears.

**Cause 1: Sonos is on a different VLAN or network segment than the Pi.**
Sonos uses UPnP/SSDP for discovery, which does not cross VLANs by default. Both the Pi and the Sonos speakers must be on the same subnet. Check your router — if you have a separate "IoT" network, either put the Pi on the same one or configure your router to allow mDNS/SSDP to pass between VLANs.

**Cause 2: Firewall blocking UPnP.**
If you have a firewall running on the Pi or a router-level firewall, it may be blocking the UDP multicast packets Sonos uses for discovery. Check your router's firewall rules and confirm UDP ports 1900 and 1901 are not blocked on the local network.

**Cause 3: Sonos speaker needs a reboot.**
If a speaker was previously detected but has disappeared, try unplugging it for 30 seconds and plugging it back in. Then reload the Sonos integration in HA.

**Cause 4: IP address changed.**
If the Sonos speaker has a dynamically assigned IP that changed, HA may lose track of it. Set a DHCP reservation for each Sonos speaker in your router so the IP stays constant.

---

## Clap Detection Service Won't Start

**Symptoms:** `systemctl status clap_service` shows "failed" or "inactive (dead)."

**Step 1: Read the full log.**

```bash
journalctl -u clap_service -n 50
```

The error message will usually point directly at the problem.

**Step 2: Verify the virtual environment.**
The service runs Python inside a virtualenv. Check it exists and has the required packages:

```bash
ls /config/aura/clap-trigger/venv/bin/python3
/config/aura/clap-trigger/venv/bin/pip list | grep -E "pyaudio|numpy|requests"
```

If the venv is missing or packages are absent, re-run the setup script:

```bash
cd /config/aura && ./scripts/setup/pi_setup.sh
```

**Step 3: Check the .env file.**
The service sources environment variables from `.env`. If the file is missing or malformed, the service will fail to start. Run:

```bash
cat /config/aura/.env
```

Every required variable must be present and have a value.

**Step 4: Check microphone permissions.**
The `clap_listener.py` script needs read access to the audio device. If running as a non-root user, it must be in the `audio` group. The systemd service file should specify `User=root` to avoid this on the Pi — verify the service file at `/etc/systemd/system/clap_service.service`.

**Step 5: Reload and try again after fixing.**

```bash
systemctl daemon-reload
systemctl start clap_service
systemctl status clap_service
```

---

## USB Microphone Not Detected

**Symptoms:** Clap detection logs show a PyAudio error about no input device, or `clap_listener.py` exits immediately with "no microphone found."

**Step 1: Confirm the mic is physically recognized.**

```bash
lsusb
```

Look for your microphone in the list. USB audio devices typically show up with a description containing "Audio" or the manufacturer name. If it does not appear, try:
- A different USB port on the Pi
- A different USB cable (some cables are charge-only with no data lines)
- A powered USB hub if you have many devices drawing power

**Step 2: Check ALSA sees the device.**

```bash
arecord -l
```

This lists all capture (input) devices. Your USB mic should appear as a card with a "USB Audio" or similar label. Note the card number and device number (e.g., card 1, device 0).

**Step 3: Update config if the card number is not 0.**
By default, `clap_listener.py` uses card 0, device 0. If your mic is on a different card, update `clap-trigger/config.yaml`:

```yaml
audio:
  card_index: 1   # change to match arecord -l output
  device_index: 0
```

Restart the service after changing this.

**Step 4: Test direct recording.**

```bash
arecord -D hw:1,0 -d 3 -f cd /tmp/test.wav
```

Replace `1,0` with your actual card and device numbers. If this command runs for 3 seconds without error, the mic is working at the ALSA level and the issue is in the config. If it errors, the mic hardware or driver is the problem.

**Step 5: Check kernel audio modules.**
On Home Assistant OS (which is based on a stripped-down Linux), some USB audio drivers may not be loaded. Check:

```bash
lsmod | grep snd_usb
```

You should see `snd_usb_audio` in the list. If not, the module needs to be loaded. This is an advanced fix — refer to the Home Assistant community forums for enabling USB audio kernel modules on HA OS.

---

## Voice Agent Won't Start

**Symptoms:** `systemctl status voice_agent` shows "failed" or the service exits immediately after starting.

**Step 1: Read the service log.**

```bash
journalctl -u voice_agent -n 50
```

The first error line will usually identify the cause directly.

**Step 2: Check ANTHROPIC_API_KEY.**
The voice agent cannot process intent without a valid Claude API key. Verify the key is set and correct in `/config/aura/.env`:

```bash
grep ANTHROPIC_API_KEY /config/aura/.env
```

The value must not be the placeholder string `your_anthropic_api_key_here`. Get the correct key from console.anthropic.com → API Keys. After updating `.env`, restart the service.

**Step 3: Check the microphone is accessible.**
The voice agent uses the same USB microphone as the clap detection service. Run the USB mic checks from the "USB Microphone Not Detected" section above. Both services can share the same mic — they use separate PyAudio streams — but the mic must be physically present and recognized by the OS.

**Step 4: Check the faster-whisper model download.**
On first run, faster-whisper downloads its speech recognition model (several hundred MB). If the Pi lost internet access mid-download, the model files may be incomplete.

Check the model cache directory:

```bash
ls ~/.cache/huggingface/hub/
```

If the directory is empty or contains only partial files, delete it and let the agent re-download on next start:

```bash
rm -rf ~/.cache/huggingface/hub/
systemctl restart voice_agent
```

Watch the log during restart — you will see download progress. This requires the Pi to have internet access.

**Step 5: Verify all Python dependencies are installed.**

```bash
/config/aura/voice-agent/venv/bin/pip list | grep -E "faster-whisper|openWakeWord|anthropic|elevenlabs|pydub"
```

If any are missing, reinstall:

```bash
pip install -r /config/aura/voice-agent/requirements.txt
```

---

## Wake Word Not Detecting

**Symptoms:** The voice agent starts without error, but saying "Hey Aura" never triggers a response. The log shows audio is being processed but no wake word events fire.

**Step 1: Run the wake word test mode.**

```bash
cd /config/aura/voice-agent
python wake_word_listener.py --test
```

In test mode the script logs the detection score for every audio chunk. Speak "Hey Aura" several times and watch the score output. A score above the threshold (default 0.5) should trigger detection.

**Step 2: Adjust the detection threshold.**
If your scores are consistently below 0.5 even when clearly saying the wake word, lower the threshold in `voice-agent/config.yaml`:

```yaml
wake_word:
  model: hey_aura
  threshold: 0.35   # lower = more sensitive, higher = less sensitive
```

Start at 0.35 and test. Do not go below 0.25 — false triggers from normal conversation become frequent below that level.

**Step 3: Check microphone input levels.**
The wake word engine needs a reasonably clean input signal. Check the mic is capturing audio at an adequate level:

```bash
arecord -D hw:1,0 -d 3 -f cd /tmp/ww_test.wav && aplay /tmp/ww_test.wav
```

Replace `1,0` with your mic's card and device numbers. Play back the recording — your voice should be clearly audible. If it is very quiet, adjust the mic gain:

```bash
alsamixer
```

Use the arrow keys to navigate to the capture device and increase the gain. Press Escape when done. A capture level of 70–85% is a good starting point.

**Step 4: Try a different OpenWakeWord model.**
The default model is trained on a specific pronunciation. If the model does not match your accent, try the `hey_jarvis` or `alexa` stock models as a test to confirm the pipeline works — then report a detection accuracy issue in the repo so we can train a better "Hey Aura" model.

Update `voice-agent/config.yaml` to test:

```yaml
wake_word:
  model: hey_jarvis
```

If a different model triggers reliably but "hey_aura" does not, the issue is model accuracy rather than the pipeline.

---

## TTS Not Speaking

**Symptoms:** The voice agent detects the wake word and processes the command, but no audio plays back through the speakers. The log shows TTS generation succeeded but you hear nothing.

**Step 1: Check the ELEVENLABS_API_KEY.**
Verify the key is set and valid:

```bash
grep ELEVENLABS_API_KEY /config/aura/.env
```

Test the key directly with a curl request:

```bash
curl -s -o /dev/null -w "%{http_code}" \
  -H "xi-api-key: YOUR_KEY_HERE" \
  https://api.elevenlabs.io/v1/voices
```

A response of `200` means the key is valid. A `401` means it is wrong or expired — regenerate it at elevenlabs.io → Profile → API Keys.

**Step 2: Check pydub and ffmpeg are installed.**
pydub requires ffmpeg to encode and play audio. Verify both are available:

```bash
python -c "import pydub; print('pydub OK')"
ffmpeg -version | head -1
```

If either command fails, install the missing dependency:

```bash
# If pydub is missing
pip install pydub

# If ffmpeg is missing (HA OS / Alpine)
apk add ffmpeg
```

**Step 3: Check the audio output device.**
The Pi may be outputting audio to HDMI rather than the USB speakers or 3.5mm jack. List output devices:

```bash
aplay -l
```

If the correct output device is not card 0, update `voice-agent/config.yaml`:

```yaml
tts:
  output_device: "hw:1,0"  # match the card and device from aplay -l
```

Test playback directly:

```bash
aplay -D hw:1,0 /tmp/ww_test.wav
```

**Step 4: Check speaker volume in HA.**
If TTS is routing through a Sonos or other HA-managed speaker, check that the `media_player` entity is not muted and the volume is above 0. In HA: go to the entity and confirm its state is not "idle" with volume 0.

**Step 5: Test TTS generation in isolation.**

```bash
cd /config/aura/voice-agent
python tts_responder.py --test "AURA test."
```

If this produces no audio and no error, add `--verbose` to see the full API response and any audio routing errors.

---

## Dashboard Won't Connect to HA

**Symptoms:** The web dashboard loads but shows "Unable to connect" or all device states display as unavailable. The browser console shows CORS errors or 401 Unauthorized.

**Step 1: Check NEXT_PUBLIC_HA_URL.**
Open `dashboard/.env.local` and confirm `NEXT_PUBLIC_HA_URL` is set to an address that your browser can reach — not just the Pi's local hostname:

```
NEXT_PUBLIC_HA_URL=http://homeassistant.local:8123
```

If you are accessing the dashboard from a different machine or the `.local` address does not resolve, use the Pi's IP address instead. Test reachability directly: open `http://homeassistant.local:8123` in the same browser — if that loads, the URL is correct.

**Step 2: Check the HA token.**
Confirm `NEXT_PUBLIC_HA_TOKEN` in `dashboard/.env.local` matches a valid long-lived access token. In HA, go to your profile → Security → Long-Lived Access Tokens. The token listed must match. If in doubt, create a new token and update `.env.local`, then restart the dev server.

**Step 3: Check CORS settings in HA.**
By default, Home Assistant only allows requests from trusted origins. If the dashboard is running on a different port or domain than HA expects, the browser will block the request with a CORS error.

To allow the dashboard origin, add it to HA's trusted origins in `configuration.yaml` on the Pi:

```yaml
http:
  cors_allowed_origins:
    - http://localhost:3000
    - https://your-vercel-deployment.vercel.app
```

After editing, restart HA: Settings → System → Restart.

**Step 4: Check the browser console.**
Open browser DevTools (F12) → Console and Network tabs. Look for the specific error:
- `401 Unauthorized` → wrong or missing HA token
- `CORS policy` errors → add the origin to HA's allowed list (Step 3)
- `ERR_CONNECTION_REFUSED` → HA is not reachable at the URL configured

**Step 5: Rebuild after changing .env.local.**
Next.js does not hot-reload `.env.local` changes. Stop the dev server and restart:

```bash
npm run dev
```

For production builds, any `.env.local` change requires a full rebuild (`npm run build`) and redeploy.

---

## Pattern Learning Not Working

**Symptoms:** The learning engine service is running but the SQLite database stays empty, event counts do not increase, or the service crashes shortly after starting.

**Step 1: Check the database path.**
Confirm the `LEARNING_DB_PATH` in `.env` points to a writable location:

```bash
grep LEARNING_DB_PATH /config/aura/.env
```

The path is relative to `/config/aura/`. The directory containing the database file must exist and be writable by the user running the service. Check:

```bash
ls -la /config/aura/learning/
```

If the `learning/` directory is missing, create it:

```bash
mkdir -p /config/aura/learning
```

**Step 2: Check the HA event listener is connected.**
The learning engine subscribes to HA state change events via the WebSocket API. Check the service log for a successful connection message:

```bash
journalctl -u learning_engine -n 30
```

You should see a line like "Connected to Home Assistant WebSocket API" and "Subscribed to state_changed events." If you see connection errors, verify `HA_URL` and `HA_TOKEN` in `.env` are correct (the same ones used by the voice agent and clap detection).

**Step 3: Check file permissions on the database file.**
If the database file was created by a different user or process, the learning engine may not be able to write to it:

```bash
ls -la /config/aura/learning/aura_learning.db
```

The file should be owned by the same user running the systemd service (root on HA OS). To fix ownership:

```bash
chown root:root /config/aura/learning/aura_learning.db
chmod 600 /config/aura/learning/aura_learning.db
```

**Step 4: Manually trigger a state change and watch the log.**
In HA, turn a light on or off while watching the learning engine log live:

```bash
journalctl -u learning_engine -f
```

You should see a log entry for the state change event within a few seconds. If the event appears in the log but is not written to the database, there is a bug in the database write path — check the full traceback in the log for the specific SQL error.

**Step 5: Check SQLite is not locked.**
If multiple processes try to write to the same SQLite file simultaneously, writes will fail with a "database is locked" error. Only one instance of the learning engine should run. Confirm only one process is active:

```bash
ps aux | grep learning_engine
```

If you see more than one process, kill the duplicates and ensure the systemd service is the only way the engine starts.

---

## Person Not Detected Correctly

**Symptoms:** `person.conaugh` or `person.adon` shows the wrong state (says "home" when the person is away, or "not_home" when they are home). Presence-based automations fire at the wrong time.

**Step 1: Check the iPhone Companion app is running.**
The Companion app must be installed and authorized on the person's iPhone. Open the app and verify it shows the correct HA server and is connected (not showing a connection error). If the app is not installed or was deleted, reinstall it from the App Store and re-authenticate.

**Step 2: Check location permissions.**
The most common cause of incorrect presence detection is the iPhone cutting off background location access.

- iPhone Settings → Privacy & Security → Location Services → Home Assistant
- Must be set to "Always" (not "While Using" — that stops reporting when the app is in the background)
- Must have "Precise Location" enabled

If the permission was changed, set it back to "Always" and wait up to 5 minutes for HA to receive an updated location.

**Step 3: Verify the device tracker is linked to the person entity.**
In HA, go to Settings → People → click the person. Under "Device trackers," confirm the correct iPhone tracker entity is listed. If it is missing, click "Add device tracker" and select the appropriate `device_tracker.` entity from the dropdown.

**Step 4: Check WiFi connection on the iPhone.**
The Companion app uses both GPS and local WiFi connection to determine presence. When the phone connects to the home WiFi network, HA treats this as a strong "home" signal. If the iPhone is not connecting to the home WiFi (for example, if it is using cellular data while physically at home), presence detection may lag.

Verify the phone is connected to the same WiFi network as the Pi. In HA: Developer Tools → States → search for the `device_tracker` entity for the phone. The `source_type` attribute will show `router` if detected via WiFi, or `gps` if detected via location.

**Step 5: Check the HA person entity state directly.**
In HA: Developer Tools → States → search `person.conaugh` or `person.adon`. The `state` value should be `home` or `not_home`. The `last_changed` timestamp shows when it last updated. If it has not updated in many hours, the Companion app has stopped sending updates — force a manual update by opening the Companion app on the phone, which triggers an immediate location report.

**Step 6: Check for multiple device trackers conflicting.**
If a person has multiple tracker entities linked (e.g., both iPhone GPS and a router-based tracker), HA uses the most optimistic one — it says "home" if any tracker says home. This can cause the person to appear "home" when they have left but their router lease has not expired. To fix: remove the router-based tracker from the person entity and rely only on the Companion app GPS tracker.
