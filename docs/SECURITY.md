# AURA Security Guide

AURA controls physical devices — door locks, cameras, climate, and all lighting. A compromised AURA instance means an attacker can unlock your door, disable your cameras, and surveil your home. This guide covers every layer of the system.

---

## Threat Model

What an attacker could do if they gain access:

- Unlock the front door remotely
- Disable or access security cameras
- Arm or disarm the alarm panel
- Open blinds / covers while you are home
- Shut down or restart the Raspberry Pi (taking AURA offline)
- Read your presence data (who is home and when)
- Access your Spotify, Govee, and ElevenLabs accounts via leaked API keys

These are not theoretical risks. Treat AURA's credentials with the same care as your bank password.

---

## 1. Network Security

### Never expose Home Assistant port 8123 to the internet

Port 8123 is the HA web interface and REST API. If this port is reachable from the internet, an attacker only needs to brute-force your HA password to gain full control of every device.

**Rule: HA must only be reachable on your local network (192.168.x.x).**

Check by running this from outside your home network (e.g., phone on mobile data):
```
curl http://YOUR_PUBLIC_IP:8123
```
If you get any response, your router is forwarding the port. Disable it immediately in your router settings.

### Use Nabu Casa or Cloudflare Tunnel for remote access — never port forwarding

If you need to access HA remotely (outside your apartment), use one of these encrypted tunnel options:

**Nabu Casa (recommended):**
- $6.50 USD/month, built into Home Assistant
- Settings -> Home Assistant Cloud -> Sign In
- Provides a `*.ui.nabu.casa` URL with automatic TLS and Cloudflare protection
- Also enables Google Home and Amazon Alexa voice integration

**Cloudflare Tunnel (free, more technical):**
- Install `cloudflared` on the Pi as a service
- Creates an encrypted tunnel from Cloudflare's edge to your Pi
- No inbound ports opened on your router
- Guide: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps

**Why not port forwarding:**
Port forwarding puts HA directly on the internet. Every scanner, bot, and automated attack tool will find and probe it within hours. Both tunnel options terminate TLS at the provider's edge — the Pi itself never needs an open inbound port.

### Put the Pi on its own network VLAN (if your router supports it)

A VLAN isolates the Pi and all smart devices from your personal devices (laptops, phones). If a smart device is compromised via its firmware, it cannot reach your MacBook or phone.

Routers that support VLANs: Unifi, pfSense, higher-end ASUS/TP-Link routers.

If your router does not support VLANs, connect the Pi via ethernet to a separate guest WiFi SSID as a partial alternative.

### Disable UPnP on your router

UPnP (Universal Plug and Play) lets devices on your network open their own inbound ports on your router without asking. Smart home devices regularly exploit this. Disable it in your router's admin panel.

Most routers: Advanced Settings -> NAT/UPnP -> Disable UPnP.

### WiFi encryption

- Use WPA3 if your router and all devices support it
- WPA2 (AES/CCMP) is acceptable — never WPA, WEP, or Open
- Use a strong WiFi password (16+ characters, not a dictionary phrase)
- Change the default router admin password — attackers know every default

---

## 2. Home Assistant Security

### Use a strong, unique password

Your HA account password must be:
- At least 16 characters
- Not reused from any other site
- Stored in a password manager (1Password, Bitwarden)

If your HA password is the same as your email, anyone who gets your email password also gets your door lock.

### Enable Multi-Factor Authentication (MFA)

Settings -> Profile -> Multi-factor Authentication Modules -> Enable TOTP

Use an authenticator app (Google Authenticator, Authy, 1Password TOTP). This means an attacker who steals your password still cannot log in without your phone.

Enable MFA for both CC and Adon's HA accounts.

### Rotate Long-Lived Access Tokens every 90 days

Long-lived access tokens are what the dashboard and voice agent use to authenticate with HA. They do not expire by default — if one is leaked, an attacker has permanent access until you revoke it.

**Rotation procedure (every 90 days):**
1. HA web UI -> Profile -> Long-Lived Access Tokens
2. Create a new token
3. Update `.env` / `.env.local` with the new token in `HA_TOKEN`
4. Redeploy the Vercel dashboard (or update the environment variable in Vercel settings)
5. Restart the voice agent on the Pi: `sudo systemctl restart aura_voice`
6. Delete the old token from HA

Keep a note of the next rotation date.

### Review and remove unused integrations

Every integration you add is a potential attack surface. Quarterly, go to:
Settings -> Devices & Services

Remove any integration you no longer use. Pay attention to any integration that has cloud access or a callback URL.

### Keep Home Assistant updated

HA releases security patches regularly. Check for updates:
Settings -> System -> Updates

Enable automatic updates for minor/patch versions if available in your HA version.

### Secure the login_attempts_threshold

The `ha_security.yaml` in this repo configures HA to lock out an IP after 5 failed login attempts. This prevents brute-force attacks against the HA login page.

This is already set in `home-assistant/security/ha_security.yaml` — ensure it is merged into your `configuration.yaml` on the Pi.

### Webhook hardening

HA webhooks are unauthenticated by nature — anyone who knows the webhook ID can fire them. Mitigations:
- Use long, random webhook IDs (not `aura_unlock_door` — use a UUID)
- Never create webhooks that directly unlock the door or disarm the alarm; use scripts that also check presence or time of day
- Review all webhooks quarterly: Settings -> Automations -> filter by webhook trigger

---

## 3. API Key Security

### Never commit .env files to git

`.gitignore` already excludes `.env` and `.env.local`. Verify with:
```bash
git status
```
If `.env` ever appears as an untracked or modified file, it means `.gitignore` is not working. Stop and fix it before committing anything.

**If you have ever accidentally committed a .env file:**
1. Revoke every key in that file immediately — assume it is compromised
2. Remove it from git history using `git filter-repo` or BFG Repo Cleaner
3. Rotate all affected credentials

### API key rotation schedule

| Service | Rotate Every | How |
|---------|-------------|-----|
| HA Long-Lived Token | 90 days | HA Profile -> Tokens |
| Anthropic API Key | 90 days | console.anthropic.com -> API Keys |
| ElevenLabs API Key | 90 days | elevenlabs.io -> Profile -> API Keys |
| Govee API Key | 180 days | Govee app -> reapply |
| Spotify Client Secret | 180 days | developer.spotify.com -> App -> Settings |

### Never share keys in chat, email, or screenshots

If you share your screen during a stream or recording and your terminal is open, check that no `.env` values are visible. If they were exposed:
1. Treat the key as compromised
2. Revoke it immediately
3. Generate a new key
4. Update all deployments

### The dashboard never exposes the HA token to the browser

All HA API calls from the dashboard go through server-side Next.js API routes (`/api/scene`, `/api/service`, `/api/auth`). The `HA_TOKEN` environment variable is only available server-side. The browser never receives it.

Do not use `NEXT_PUBLIC_HA_TOKEN` — the `NEXT_PUBLIC_` prefix makes a variable available in browser JavaScript bundles.

---

## 4. Web Dashboard Security

### Authentication

Set `DASHBOARD_AUTH_TOKEN` in your Vercel environment variables to a strong, random string. This gates the entire dashboard behind an access code that CC and Adon enter once per 30 days (stored in a `httpOnly` cookie).

Generate a strong token:
```bash
openssl rand -base64 32
```

The middleware (`dashboard/src/middleware.ts`) enforces this on every request. The auth route (`/api/auth`) sets an `httpOnly`, `sameSite=strict`, `secure` cookie — it cannot be read by JavaScript and cannot be sent cross-origin.

### Rate limiting

The middleware rate-limits all `/api/*` routes to 60 requests per minute per IP. This prevents automated scanners from hammering your scene and service endpoints.

### Security headers

Every response from the dashboard includes:
- `X-Content-Type-Options: nosniff` — prevents MIME-type sniffing attacks
- `X-Frame-Options: DENY` — prevents the dashboard from being embedded in iframes (clickjacking)
- `X-XSS-Protection: 1; mode=block` — legacy XSS filter for older browsers
- `Referrer-Policy: strict-origin-when-cross-origin` — limits referrer leakage
- `Content-Security-Policy` — restricts which scripts, styles, and connections are allowed

### CORS

HA is configured (via `ha_security.yaml`) to only accept CORS requests from your Vercel domain and `localhost:3000`. Update the `cors_allowed_origins` list with your actual Vercel URL after deployment.

### Production checklist before making the dashboard public

- [ ] `DASHBOARD_AUTH_TOKEN` is set in Vercel environment variables
- [ ] `HA_TOKEN` is set in Vercel (server-side only, not `NEXT_PUBLIC_`)
- [ ] Your Vercel domain is listed in HA's `cors_allowed_origins`
- [ ] The dashboard URL is not posted publicly (treat it as a secret URL)
- [ ] MFA is enabled on your Vercel account

---

## 5. Voice Agent Security

### Voice commands are processed locally — mostly

The pipeline:
1. Wake word detection (OpenWakeWord) — runs entirely on the Pi, offline
2. Speech-to-text (faster-whisper) — runs on the Pi, offline
3. Intent processing — the transcribed **text** is sent to the Anthropic API
4. TTS generation — the response **text** is sent to ElevenLabs

Raw audio never leaves your apartment. What does leave: the text transcript of what you said, and AURA's text response. Both are sent over HTTPS to Anthropic and ElevenLabs respectively. Both companies' privacy policies apply.

For maximum privacy, you could run a local LLM (Ollama) instead of the Anthropic API — this is a future option.

### Voice PIN for sensitive actions

The voice security module (`voice-agent/security.py`) requires a spoken PIN before executing:
- `lock.unlock` — unlocking the front door
- `lock.lock` — locking the front door
- `alarm_control_panel.alarm_disarm` — disarming the alarm
- `camera.disable_motion_detection` — disabling cameras

Configure your PIN with `AURA_VOICE_PIN` in `.env` (recommended) or `voice-agent/config.yaml` under `security.voice_pin`. **Do not leave it at `CHANGE_ME` or any default value before going live.**

After 3 failed PIN attempts, the voice agent locks out PIN verification for 5 minutes.

These actions are completely blocked from voice control regardless of PIN:
- `homeassistant.stop` — shutting down HA
- `homeassistant.restart` — restarting HA
- `hassio.host_shutdown` — shutting down the Pi
- `hassio.host_reboot` — rebooting the Pi

These must be done physically or through the HA admin interface.

### USB microphone privacy

The clap detection microphone (`clap-trigger/clap_listener.py`) only processes amplitude levels — it does not record or transmit audio. The voice agent microphone records speech only after the "Hey Aura" wake word is detected; it is not always recording speech.

However, both microphones are always listening for audio patterns. Be aware of this when having sensitive conversations in the apartment.

---

## 6. Physical Security

### Pi placement

The Pi should be in a location not visible from windows or the front door. If someone can see the Pi, they know you have a smart home system and may target it physically.

Suggested locations: inside a TV cabinet, behind a monitor, in a utility closet with ethernet run to it.

### Always keep a physical key backup

Never rely solely on the smart lock. If the Pi goes offline, HA becomes unreachable, or your phone dies:
- You must be able to get into your apartment
- Physical key backup is non-negotiable

Test the physical key every few weeks to ensure it has not been lost.

### SD card backup

The Pi's SD card contains all your HA configuration. If it fails:
- All automations, scenes, integrations, and tokens are gone
- You would need to reconfigure everything from scratch

Back up the SD card periodically:
1. HA web UI -> Settings -> System -> Backups -> Create Backup
2. Download the backup to your desktop
3. Store a copy offsite (encrypted cloud storage)

---

## 7. Client Deployment Security

When deploying AURA for a paying client:

- Each client gets a completely separate HA instance on their own Pi
- Each client gets their own HA account, their own Long-Lived Token, their own `.env`
- Never reuse tokens or API keys between clients
- Client configs live in `clients/{client_name}/` — never modify base configs for a client
- When a client churns (cancels service):
  1. Revoke the HA Long-Lived Token for that deployment
  2. Remove any OASIS accounts or API keys provisioned for that client
  3. Factory reset the Pi if it is being returned
  4. Delete the client folder from the repo after archiving it

---

## 8. Incident Response

If you suspect AURA has been compromised:

1. **Immediately:** Revoke the HA Long-Lived Token (HA Profile -> Tokens -> Delete all)
2. **Immediately:** Change your HA account password
3. **Immediately:** Physically lock your door (do not rely on the smart lock until the system is secured)
4. **Within the hour:** Rotate all API keys listed in Section 3
5. **Within the hour:** Check HA logs for unauthorized service calls: Settings -> System -> Logs
6. **Within 24 hours:** Review all automations for any you did not create
7. **Within 24 hours:** Check your router logs for any unexpected outbound connections from the Pi's IP
8. **If the door was unlocked:** File a police report and document the HA logs as evidence

Signs of a compromised system:
- Lights turning on/off at unexpected times without explanation
- The door lock status changing without anyone triggering it
- Unknown devices appearing in HA's device registry
- The Pi rebooting unexpectedly
- HA logs showing service calls from unfamiliar IPs

---

## 9. Security Review Checklist

Run through this checklist every 90 days:

**Authentication:**
- [ ] HA passwords are strong and not reused
- [ ] MFA is enabled on both HA accounts (CC + Adon)
- [ ] Long-Lived Access Tokens have been rotated
- [ ] Dashboard auth token has been rotated

**API Keys:**
- [ ] Anthropic API key rotated
- [ ] ElevenLabs API key rotated
- [ ] Govee API key still valid and not shared

**Network:**
- [ ] Port 8123 is NOT reachable from the internet (test from mobile data)
- [ ] UPnP is disabled on the router
- [ ] No unexpected port forwards in router settings

**HA Configuration:**
- [ ] Unused integrations removed
- [ ] All automations reviewed — none that you did not create
- [ ] HA is on the latest version

**Backups:**
- [ ] HA backup created and downloaded to desktop
- [ ] Backup stored offsite

**Voice Agent:**
- [ ] Voice PIN is set via `AURA_VOICE_PIN` or `voice-agent/config.yaml` and is not `CHANGE_ME`
- [ ] voice-agent/security.py is integrated into the intent pipeline
