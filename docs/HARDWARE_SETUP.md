# AURA Hardware Setup — Complete Beginner Guide

This guide is for someone who has never touched a Raspberry Pi, never flashed an SD card, and has no hardware background. If that's you, you're in the right place. Read every word — nothing here assumes prior knowledge. Each step tells you exactly what to look at, what to touch, and what to expect.

Estimated time: 30–45 minutes for hardware setup. Another 20–30 minutes to finish software setup.

---

## What You Are Building

You are setting up a small, cheap computer called a Raspberry Pi that will run Home Assistant — the software brain of AURA. This Pi sits next to your router and runs 24 hours a day, 7 days a week. It has no screen, no keyboard, no mouse. Once it is set up, you control everything through a web browser on your laptop or phone.

Think of it like a tiny server in your house. It wakes up, connects to your WiFi, and starts talking to your smart lights, plugs, speakers, and locks. You never need to physically touch it again after setup.

---

## What to Buy (Exact Links Not Needed — Search These Names)

Before you start, you need these items. If you already have some of them, skip those.

### Required

**Raspberry Pi 5 — 8GB version**
This is the actual computer. Search "Raspberry Pi 5 8GB" on Amazon or go to raspberrypi.com. It costs roughly $80–100 CAD. Buy the 8GB version, not the 4GB — Home Assistant runs better with more memory.

**microSD Card — 32GB or larger**
This is the Pi's hard drive. The entire operating system lives on this tiny card. Search "SanDisk Ultra 32GB microSD" or "SanDisk Extreme 32GB microSD A2". Buy one rated A1 or A2 (this is a speed rating printed on the card). A2 is better. 32GB is the minimum; 64GB is fine too. Cost: $8–15 CAD.

**Raspberry Pi 5 Power Supply — Official, 27W USB-C**
Search "Raspberry Pi 5 official power supply" or "Raspberry Pi 27W USB-C power supply". Do not substitute a phone charger here. Phone chargers do not supply enough power and the Pi will randomly crash, freeze, or refuse to boot. The official supply is labeled "5.1V 5A" and has the Raspberry Pi logo. Cost: $12–20 CAD.

**Ethernet Cable**
A regular network cable. One end goes into the Pi, the other into your router. You probably have one already — look behind your TV or in a drawer. If not, any "Cat 5e" or "Cat 6" cable from Amazon works. 6 feet is usually enough. Cost: $5–10 CAD.

**Case for the Pi**
A plastic or metal enclosure that the Pi board clips into. It protects the board from dust, static, and accidental damage. Good options: the official Raspberry Pi 5 case, or the Argon ONE V3 (metal, looks nicer, runs cooler). Search those names. Cost: $15–35 CAD.

**microSD Card Reader (for your laptop)**
This is how you write software to the SD card from your Windows laptop. Check right now: does your laptop have a card slot on the side? It looks like a thin rectangular slot, sometimes labeled "SD". If yes, look for a microSD-to-SD adapter — a small plastic piece that the tiny microSD card clicks into (it often comes in the SD card package, taped to the card). If your laptop has no card slot at all, buy a USB microSD card reader. Search "USB microSD card reader". It looks like a small USB thumb drive with a slot in it. Cost: $8–12 CAD.

### Optional (Can Add Later)

**USB Microphone**
Needed for clap detection and the voice agent. Any basic USB microphone works. Search "USB desktop microphone" or "Blue Snowball iCE". Cost: $15–50 CAD. You can skip this for now and add it later.

---

## Step 1 — Understand What Each Thing Looks Like

Before you assemble anything, hold each item and read this. Knowing what you are holding matters.

### The Raspberry Pi 5 Board

The Pi is a green circuit board roughly 85mm x 56mm — slightly bigger than a credit card but thicker. It is covered in chips, components, and traces.

**Look at it from above.** One of the short edges has most of the ports. Going left to right you will see:

- Two USB 3.0 ports — these are the standard rectangular USB-A ports, stacked on top of each other. They are blue inside, which indicates USB 3.0.
- Two USB 2.0 ports — same shape as the USB 3.0 ports but black inside. These are the older, slower USB ports. Fine for keyboards, mice, and microphones.
- One ethernet port — this is slightly wider than a USB port. It has a plastic clip on one side of the cable (like a phone plug but bigger). This is where your internet cable goes.

**Look at the other short edge.** You will see:

- Two HDMI ports — these are the small "micro HDMI" size, not the full-size HDMI you plug into a TV. They are smaller and thinner than what you probably think of as HDMI. You do not need these — AURA runs headless (no monitor).
- One USB-C port — this is the oval-shaped port, same as what modern phones and laptops use. On the Pi 5, this is labeled with a power symbol or "PWR IN". This is where the power supply goes.
- One 3.5mm headphone jack — the small round audio port. You won't use this.

**Look at the underside of the board.** You will see the microSD card slot — a thin metal slot near one of the corners. This is where the SD card goes.

**The GPIO pins** — along one of the long edges of the board, you will see two rows of small metal pins sticking up. These are used for hardware projects. Do not touch them and do not worry about them for AURA.

### The microSD Card

Hold it in your hand. It is the size of a fingernail — roughly 15mm x 11mm. One side has a label printed on it (the brand name, capacity, and speed rating). The other side has gold contact strips along the bottom edge. There is a small notch cut into one corner.

### The Power Supply

It looks like a phone wall charger with a USB-C cable permanently attached. The brick plugs into a standard wall outlet. The cable ends in a USB-C connector — the small oval plug. One side of the USB-C connector is flat; the other is slightly curved. It is reversible, meaning you can insert it either way.

### The Case

It is an enclosure in two or more pieces. There is a bottom tray that the Pi board sits in, and a top cover that snaps or screws on. The sides of the case have cutouts matching the Pi's ports so you can still plug cables in once the Pi is inside. Look at the case and find where the ports will be before you start assembling.

---

## Step 2 — Flash the SD Card

"Flashing" means writing software onto the SD card. You are putting the Home Assistant operating system onto the card so the Pi knows what to do when it boots up. You do this on your laptop, not on the Pi.

### 2.1 — Download Home Assistant

1. On your laptop, open a web browser.
2. Go to: `https://www.home-assistant.io/installation/raspberrypi`
3. You will see a list of Raspberry Pi models. Click **Raspberry Pi 5**.
4. Look for the download button for "Home Assistant OS". Click it.
5. The file that downloads will be named something like `haos_rpi5-64-13.2.img.xz`. The exact version number does not matter — download whatever the current version is.
6. Save it to your Downloads folder. The file is about 300–500MB. Wait for it to finish downloading fully before moving on.
7. Do not extract or unzip this file. Leave it as-is. The flashing tool will handle it.

### 2.2 — Download Balena Etcher

Balena Etcher is the free tool that writes the Home Assistant image to your SD card.

1. Go to: `https://etcher.balena.io`
2. Click "Download Etcher".
3. Choose the Windows version (it should auto-detect your OS).
4. Download and install it like any normal Windows app — double-click the installer, click through the prompts.

### 2.3 — Insert the SD Card Into Your Laptop

This is the step that confuses most people the first time.

**If your laptop has an SD card slot on the side:**
The built-in slot is for full-size SD cards. Your microSD card is too small to fit directly. You need the microSD-to-SD adapter — the plastic piece the card may have come clipped into. It looks like a full-size SD card with a slot at one end. Slide the microSD card (gold pins facing down, notch corner matching the adapter's corner) into the adapter until it clicks. Now insert the adapter into your laptop's SD card slot with the label facing up.

**If your laptop has no card slot:**
Plug your USB microSD card reader into any USB port on your laptop. It does not matter which USB port. Insert the microSD card into the reader (gold pins going in first). The reader will mount like a USB thumb drive.

Either way, Windows may pop up a notification that says "What do you want to do with this drive?" — click "Do nothing" or close it.

### 2.4 — Flash the Card

1. Open Balena Etcher.
2. Click **"Flash from file"**.
3. A file browser opens. Navigate to your Downloads folder and select the `.img.xz` file you downloaded.
4. Click **"Select target"**.
5. A list of drives appears. You should see your SD card listed — it will show the capacity you bought (e.g., "31.9 GB" for a 32GB card) and a label like "Generic Storage Device" or "SanDisk".
6. **Critical step**: Do not check your laptop's main drive. The main drive will show a much larger capacity (250GB, 512GB, 1TB, etc.) and will be labeled "System Drive" or something similar. Only check the small removable drive.
7. Click **"Select"** once you have checked the right drive.
8. Click **"Flash!"**.
9. Windows will ask for admin permission — click Yes.
10. Etcher will write the image to the card. A progress bar shows the percentage. This takes 3–8 minutes.
11. After writing, Etcher automatically verifies the card. Wait for that too.
12. When it says **"Flash Complete!"** you are done.
13. Close Etcher.

### 2.5 — Remove the SD Card

**Before pulling the card out**, eject it safely:
1. Look in the system tray (bottom-right of your taskbar, near the clock).
2. Click the small USB/drive icon (it looks like a USB plug with a checkmark).
3. Click "Eject" next to your SD card.
4. Windows will say "Safe to remove hardware".
5. Now remove the card (press it in slightly and it will spring out, or just pull it out of the USB reader).

The card is now ready. Do not plug it into your laptop again.

---

## Step 3 — Assemble the Pi

### 3.1 — Put the Pi Into Its Case

1. Take the bottom tray of the case.
2. Hold the Pi board so the port-heavy edge (USB ports, ethernet) faces the side of the case that has the largest openings/cutouts. The ports need to stick out through those holes.
3. Lower the Pi board into the bottom tray. It will either sit on small posts (standoffs) that click into the board's corner holes, or it will simply rest flat on the tray. Refer to the case's included instructions if needed — every case is slightly different, but none require tools for basic assembly.
4. Press the board down gently until it sits flat and secure.
5. Do not attach the top cover yet. You need to insert the SD card first.

### 3.2 — Insert the microSD Card

1. Look at the underside of the Pi board. You will see the microSD card slot — a thin metal slot with a spring mechanism inside.
2. Hold the microSD card with the label side facing away from the Pi board (facing down, toward the floor) and the gold contact strips facing up (toward the board).
3. The card slots in from the side, sliding horizontally. Align the card with the slot.
4. Gently push the card into the slot. You will feel a slight click when it is fully seated.
5. If it does not go in easily, stop. You may have it upside down. Flip the card and try again. Never force it.
6. Once inserted, the card should sit flush or very slightly proud of the edge — it should not wobble.

### 3.3 — Attach the Case Cover

1. Place the top cover onto the case.
2. Snap or screw it down according to your case's design.
3. All ports should be visible and accessible through the case openings.

---

## Step 4 — Connect the Cables

Do this in order. The order matters because power is always last.

### 4.1 — Ethernet Cable

Look at the Pi's ethernet port — it is the widest port on the board, located on the short edge near the USB ports. It looks like an oversized phone jack.

The ethernet cable's plug has a small plastic clip on one side. Hold the cable so the clip is on the bottom. Align the plug with the port and push it in. You will hear a definite click when it is fully seated. If it does not click, it is not in all the way — push firmer.

Plug the other end of the ethernet cable into any available port on your router. Your router is the box your internet comes into — it usually sits near your TV stand, desk, or in a closet. The ethernet ports on the router are usually grouped together on the back. Any port works; there is no specific port to use.

### 4.2 — USB Microphone (Optional, Can Skip for Now)

If you have a USB microphone and want to set it up now, plug it into any of the USB ports on the Pi. The USB-A ports (the standard rectangular ones) are on the same edge as the ethernet port. Any of the four USB ports works. Push the cable in until it is firm — USB-A plugs do not click, they just stop moving.

If you do not have a microphone yet, skip this. You can add it later without any reinstallation.

### 4.3 — Power Supply (Last)

The power supply is the last thing you connect.

Find the USB-C port on the Pi that is labeled for power. On the Pi 5, it is the USB-C port on the edge opposite the GPIO pins — it is slightly away from the HDMI ports, toward the corner of the board. If your case has labels on the outside, it will be marked "PWR" or have a power symbol.

Hold the USB-C connector and insert it into the Pi's power port. USB-C is reversible — you cannot insert it wrong side up. Push until it is fully seated.

Plug the other end (the wall plug) into any standard wall outlet.

### What Happens When Power Is Connected

Within a few seconds, you will see lights on the Pi:
- A **solid red LED** means the Pi has power. This should appear immediately.
- A **green LED that blinks rapidly and irregularly** means the Pi is reading the SD card and booting. This is good.

The **first boot takes 5 to 10 minutes**. During first boot, Home Assistant is setting itself up on the card for the first time. This is normal. Do not unplug the Pi during this time.

When the green LED slows down or becomes steady, the Pi is ready.

If you never see any LEDs: check that the power supply is plugged into the wall. Check that the USB-C cable is fully seated in the Pi's power port. Check that the wall outlet has power (test it with a phone charger).

---

## Step 5 — Access Home Assistant from Your Laptop

The Pi is now running. You access it entirely through a web browser.

### 5.1 — Connect Your Laptop to the Same Network

Your laptop must be connected to the same router the Pi's ethernet cable is plugged into. If your laptop is on WiFi, that WiFi must come from the same router. This is almost certainly already the case if you are at home.

### 5.2 — Open Home Assistant

1. On your laptop, open any web browser (Chrome, Edge, Firefox).
2. In the address bar at the top, type exactly: `http://homeassistant.local:8123`
3. Press Enter.

If a "Preparing Home Assistant" screen loads, or if you see a welcome/setup page, you are in. Skip ahead to Step 5.4.

**If the browser says "This site can't be reached" or "ERR_NAME_NOT_RESOLVED":**

Wait 5 more minutes. The Pi may still be booting. Then try again.

If it still does not work after 10 minutes, you need to find the Pi's IP address using your router:

1. Open a new browser tab.
2. Type your router's address. Most home routers use `192.168.1.1` or `192.168.0.1`. Try both. The sticker on the back or bottom of your router often shows the correct address.
3. Log in to the router. The username and password are usually on the same sticker on the router. Common defaults are "admin" / "admin" or "admin" / "password".
4. Look for a section called "Connected Devices", "DHCP Clients", "Device List", or "LAN Clients".
5. Find a device named "homeassistant" or "raspberrypi".
6. Note its IP address — it looks like four numbers separated by dots, e.g., `192.168.1.105`.
7. Go back to your browser and type: `http://192.168.1.105:8123` but replace `192.168.1.105` with the actual IP address you found.

### 5.3 — Understand the Setup Screen

The first time you reach Home Assistant, it will show a loading or preparation screen. Home Assistant is finishing its first-time setup. This can take another 3–5 minutes even after you reach the page. The screen will update on its own when it is ready.

When it is ready, you will see a page with a "Create Account" prompt.

### 5.4 — Create Your Account

1. Enter a name — your name, or "CC", whatever you want.
2. Enter a username — lowercase, no spaces (e.g., `cc` or `conaugh`).
3. Enter a password. Make this a real password. This account controls your lights, locks, cameras, and everything else. Use your password manager.
4. Click "Create Account".
5. On the next screen, it asks for your home location. Type your city. This is used for things like "turn lights on at sunset" — it needs to know your timezone and your local sunrise/sunset times.
6. Set your timezone.
7. Home Assistant may detect some devices on your network automatically and show them to you. You can click "Finish" to skip this for now — you will add devices properly later using SETUP_GUIDE.md.
8. You are now looking at the Home Assistant dashboard.

The Pi is up and running. Home Assistant is live. You accessed it from your browser without ever connecting a monitor or keyboard to the Pi.

---

## Step 6 — Install the SSH Add-on

SSH is how you access the Pi's command line from your browser. You will need this to run AURA's setup scripts.

1. In Home Assistant, look at the left sidebar. Click the **Settings** icon — it looks like a gear and is near the bottom of the sidebar.
2. Click **Add-ons**.
3. In the bottom-right corner of the Add-ons page, click **Add-on Store**.
4. In the search field at the top of the store, type: `Advanced SSH`
5. A result called **"Advanced SSH & Web Terminal"** should appear. Click it. Make sure it says "Advanced" in the name — there is a simpler version too, but the Advanced one is what you need.
6. Click **Install**. Wait. This takes about 2 minutes.
7. Once installed, click the **Configuration** tab near the top of the add-on page.
8. Find the toggle labeled **"Protection Mode"**. It is ON by default. Turn it **OFF**.
9. Click **Save** at the bottom of the configuration section.
10. Go back to the **Info** tab.
11. Click **Start**.
12. Find the toggle that says **"Show in sidebar"** and turn it ON.

You will now see "Advanced SSH & Web Terminal" in the left sidebar. Click it anytime to open a command line for the Pi.

---

## Step 7 — Install the ha-mcp Add-on

ha-mcp is the bridge that lets Claude Code on your laptop talk to Home Assistant on the Pi.

1. Go to **Settings** → **Add-ons** → **Add-on Store**.
2. In the top-right corner of the store, click the three-dot menu icon (three vertical dots).
3. Click **Repositories**.
4. In the text field, paste: `https://github.com/homeassistant-ai/ha-mcp`
5. Click **Add**.
6. Click **Close**.
7. The page may refresh. Scroll down in the store until you find an add-on called **ha-mcp**.
8. Click it, then click **Install**.
9. Once installed, click **Start**.

---

## Step 8 — Create Your Long-Lived Access Token

This is a special password that AURA's code uses to communicate with Home Assistant through its API. You generate it once and store it in your `.env` file.

1. In Home Assistant, look at the bottom of the left sidebar.
2. Click on your **user profile** — it is a circle with your initial or the word "Profile". It is the very bottom icon.
3. On your profile page, scroll all the way down. Near the bottom, you will see a section called **"Long-Lived Access Tokens"**.
4. Click **"Create Token"**.
5. A dialog box appears asking for a name. Type `AURA` (or anything descriptive).
6. Click **OK**.
7. A long string of characters appears in the dialog. This is your token. It looks like a random 150-character string.
8. **Copy this token immediately.** Click on the text and select all (Ctrl+A), then copy (Ctrl+C). Paste it into a notepad file or your password manager right now.
9. Click **Close** on the dialog.

You cannot view this token again after closing the dialog. Home Assistant does not store a retrievable copy — it only stores a hash. If you lose it, you just delete the token and create a new one. But copy it now before closing.

---

## Step 9 — Set Up the AURA Repository

Open the SSH terminal in Home Assistant (click "Advanced SSH & Web Terminal" in the sidebar). You will see a black terminal screen with a command prompt. This is the Pi's command line.

Type or paste each of the following commands, pressing Enter after each one. Wait for each command to finish before typing the next.

**Install git (git is not installed on HA OS by default):**
```
apk add git
```

**Move into the Home Assistant config directory:**
```
cd /config
```

**Clone the AURA repository:**
```
git clone https://github.com/CC90210/Aura-Home-Agent.git aura
```

**Move into the aura folder:**
```
cd aura
```

**Create your local environment file from the template:**
```
cp .env.example .env
```

**Open the environment file for editing:**
```
nano .env
```

The `nano` editor opens. You will see the contents of the `.env` file on screen. Use your arrow keys to move the cursor to each variable. Fill in the following:

- `HA_TOKEN=` — paste the token you copied in Step 8
- `ANTHROPIC_API_KEY=` — your Anthropic API key from console.anthropic.com
- `ELEVENLABS_API_KEY=` — your ElevenLabs API key from elevenlabs.io
- `ELEVENLABS_VOICE_ID=` — the voice ID you want AURA to use (found in your ElevenLabs account)
- `HA_URL=` — set this to `http://homeassistant.local:8123`

To save and exit nano: press **Ctrl+X**, then press **Y**, then press **Enter**.

**Run the setup script:**
```
bash scripts/setup/pi_setup.sh
```

This installs Python dependencies and registers AURA's services (clap detection, voice agent). It takes 10–15 minutes. Let it run.

**Verify the installation:**
```
bash scripts/setup/verify_install.sh
```

You should see a list of checks. Green passes for required items is the goal. Items marked SKIP are optional and fine to ignore.

---

## Step 10 — Continue With the Main Setup Guide

The hardware is set up. Home Assistant is running. The AURA services are installed.

From here, continue with `docs/SETUP_GUIDE.md` starting at the step for adding smart devices. That guide covers:
- Adding Govee LED strips to Home Assistant
- Adding TP-Link Kasa smart plugs
- Connecting Spotify
- Deploying Home Assistant YAML configs (automations, scenes)
- Setting up the web dashboard on your phone and iPad
- iPhone presence detection

All of those steps happen in the Home Assistant web UI and are point-and-click. The hard part — getting the Pi running — is done.

---

## What Is Physically Plugged Into the Pi

When everything is assembled, the Pi should have exactly these things connected:

```
[Wall Outlet] → [Official Pi 27W Power Supply] → [Pi USB-C Power Port]
[Router] ←ethernet cable→ [Pi Ethernet Port]
[USB Microphone] → [Any Pi USB Port]         (optional)
```

That is it. Three cables at most.

Everything else in AURA — Govee LEDs, smart plugs, Sonos speakers, SwitchBot blinds — communicates over your WiFi network. Those devices plug into their own wall outlets. They are not connected to the Pi physically. The Pi talks to them over the air.

---

## Troubleshooting

**The Pi shows no LEDs at all after plugging in power.**
Check that the wall outlet has power. Check that the USB-C cable is fully inserted into the Pi's power port (push harder — it needs to seat firmly). Make sure you are using the official power supply and not a phone charger.

**The green LED blinks for a minute then stops. Nothing loads in the browser.**
The SD card may not have flashed correctly. Remove the SD card from the Pi, re-flash it using Etcher on your laptop, and try again. Make sure to re-flash from the original `.img.xz` file, not from a copy.

**`http://homeassistant.local:8123` does not load.**
Wait 10 minutes after first power-on. If it still does not load, find the Pi's IP address through your router's admin page (described in Step 5.2) and use that address instead. Some Windows networks have issues resolving `.local` addresses — the IP address method always works.

**Home Assistant loads but says it is "Preparing" for more than 15 minutes.**
This happens if the Pi has a slow SD card or a weak power supply. Make sure you are using an A1 or A2 rated SD card and the official 27W power supply. If it has been sitting at "Preparing" for more than 30 minutes, power cycle the Pi (unplug and replug the power supply) and wait again.

**The SSH add-on won't start or gives a permission error.**
Make sure you turned off Protection Mode in the add-on's Configuration tab and clicked Save before starting the add-on.

**`nano .env` shows an empty file or doesn't have the right variables.**
Make sure you ran `cp .env.example .env` first. If `.env.example` doesn't exist, the repository may not have cloned correctly. Run `ls` to see what files are in the directory, and re-clone if needed.

**The setup script fails with a permissions error.**
Make sure Protection Mode is OFF on the Advanced SSH add-on.

For issues not listed here, see `docs/TROUBLESHOOTING.md`.
