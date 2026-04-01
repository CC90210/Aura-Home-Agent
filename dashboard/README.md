# AURA Dashboard

The AURA dashboard is a Next.js web app that gives you full control over your smart apartment from any browser, phone, or wall-mounted tablet. Dark, futuristic UI with scene controls, climate, music, habit tracking, and system status. It talks directly to your Home Assistant instance, so every button press controls a real device in the apartment.

---

## Running Locally (Development)

1. Open a terminal and run `cd dashboard` from the repo root
2. Copy `.env.example` to `.env.local`: `cp .env.example .env.local`
3. Open `.env.local` and fill in your values:
   - `HA_URL` = `http://homeassistant.local:8123` (works while on the same WiFi as the Pi)
   - `HA_TOKEN` = your long-lived access token from the HA web UI
   - `NEXT_PUBLIC_HA_URL` = same value as `HA_URL`
4. Run `npm install`
5. Run `npm run dev`
6. Open http://localhost:3000

---

## Deploying to Vercel (Production)

Vercel is a free hosting platform built for Next.js. You get a public URL that works from any device, anywhere. The free tier is more than enough for this use case.

### Prerequisites

- The AURA repo must be pushed to GitHub (github.com)
- You need a Vercel account (free)

### Steps

**1. Create your Vercel account**

Go to vercel.com and click "Sign Up". Choose "Continue with GitHub" — this links your repos automatically and is the easiest path.

**2. Add a new project**

Once logged in, click "Add New" in the top right, then select "Project".

**3. Import the repository**

Vercel will show your GitHub repos. Find `Aura-Home-Agent` (or whatever you named the repo) and click "Import".

**4. Set the Root Directory**

This step is critical. The dashboard lives in a subdirectory, not at the root of the repo, so Vercel needs to know where to look.

- Under "Configure Project", find the "Root Directory" field
- Click "Edit" next to it
- Type `dashboard` and confirm

If you skip this step, the build will fail.

**5. Confirm the framework preset**

Vercel auto-detects Next.js. Under "Framework Preset" it should already say "Next.js". Leave it as is.

**6. Add environment variables**

Still on the same "Configure Project" screen, scroll down to "Environment Variables". Add these three:

| Name | Value |
|------|-------|
| `HA_URL` | Your Home Assistant URL (see "Accessing From Outside Your Home" below) |
| `HA_TOKEN` | Your long-lived access token from HA (Profile -> Long-Lived Access Tokens) |
| `NEXT_PUBLIC_HA_URL` | Same URL as `HA_URL` |

Do not use `http://homeassistant.local:8123` here — that address only resolves on your local network. Use a remote-accessible URL instead (see next section).

**7. Deploy**

Click "Deploy". Vercel builds and deploys the app. First deploy takes about 60-90 seconds.

**8. Get your URL**

After deployment, Vercel shows a URL like `aura-dashboard-xxx.vercel.app`. This is your live dashboard. You can set a custom domain later if you want something cleaner.

**9. Add it to your phone as an app**

On your iPhone or iPad, open Safari and go to your Vercel URL. Tap the Share button (the box with an arrow), then tap "Add to Home Screen". Name it "AURA". It will appear on your home screen and open as a full-screen app with no browser chrome.

---

## Accessing From Outside Your Home

By default, Home Assistant only responds to requests from devices on your local WiFi network. The Vercel dashboard is hosted on the internet, so it needs a Home Assistant URL that is reachable from anywhere. Pick one of the following options before you deploy.

**Option A — Nabu Casa (Recommended)**

Nabu Casa is Home Assistant's official remote access service. $6.50/month. Takes five minutes to set up and requires no networking knowledge.

- In the HA web UI go to Settings -> Home Assistant Cloud
- Sign up and enable Remote UI
- You get a URL like `https://your-name.ui.nabu.casa`
- Use that URL as `HA_URL` and `NEXT_PUBLIC_HA_URL` in your Vercel environment variables

This is the right choice unless you have a specific reason to avoid a paid service.

**Option B — Cloudflare Tunnel (Free)**

Cloudflare Tunnel creates a secure, encrypted connection from your Pi to Cloudflare's network, which then gives you a public URL. It is free and more private than port forwarding, but requires some command-line setup on the Pi.

- Install the `cloudflared` add-on from the HA add-on store (community add-ons)
- Follow the Cloudflare Tunnel setup to get a permanent subdomain
- Use the resulting `https://` URL in your Vercel environment variables

**Option C — Port Forwarding (Not recommended)**

You can forward port 8123 on your home router to the Pi's local IP. This works but it directly exposes your Home Assistant to the public internet, which is a security risk. Avoid this unless you fully understand the implications and have HA's security settings locked down.

---

## Wall-Mounted iPad Setup

1. Complete the Vercel deployment steps above
2. On the iPad, open Safari and navigate to your Vercel URL
3. Tap the Share button -> "Add to Home Screen"
4. Name it "AURA" and tap "Add"
5. Open the app from the home screen — it runs full-screen with no browser chrome
6. To lock the iPad to this app: Settings -> Accessibility -> Guided Access -> turn it on, then triple-click the side button while the app is open to start a session
7. Choose a mounting location — above a light switch or beside the front door works well
8. Use a magnetic wall mount or a low-profile adhesive bracket
9. Route a USB-C charging cable behind the wall or along the baseboard so the iPad stays powered indefinitely
