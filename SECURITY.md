# Security Policy — Aura (Life / Home Agent)

Aura is the ambient life-and-home agent of the OASIS AI C-Suite — it runs
on a Raspberry Pi 5 hub, controls Home Assistant and physical devices
(door locks, cameras, lights, thermostats), and orchestrates daily
routines via voice. **Physical-device control is inherently higher-risk
than API calls** — a software bug can open a front door.

## Reporting a Vulnerability

**Do not open a public GitHub issue for a security vulnerability.**

Please email **security@oasisai.work** (preferred) or
**conaugh@oasisai.work** (fallback) with:

- A description of the issue
- Steps to reproduce (or a proof-of-concept)
- The affected version or commit SHA
- Your assessment of impact — especially highlight anything that could
  affect physical safety (locks, cameras, alarm systems)

**Response SLA**

| Stage | Target |
|-------|--------|
| Initial acknowledgement | within 48 hours |
| Severity triage | within 5 business days |
| Fix in `main` for critical/high | within 14 days |
| Physical-device safety bugs | immediate — no 14-day window |
| Coordinated public disclosure | 90 days from report, or sooner if a fix ships |

We will credit you in the fix commit and changelog unless you ask to stay
anonymous.

## Supported Versions

Only the latest commit on `main` is actively maintained. Forks and older
tags are not patched. If you are running a pinned commit older than 30
days, pull `main` before reporting — the issue may already be fixed.

## Security Posture

Aura is installed through the OASIS AI setup wizard
(`github.com/CC90210/CEO-Agent`). The wizard enforces the shared
credential posture:

### Credential handling

- All secrets live in a single `.env.agents` file per install — never
  in source, never in git history, never in CI logs.
- `.env.agents` is in `.gitignore` and `.git/info/exclude`; the setup
  wizard refuses to write to any `.env*` path that is tracked by git.
- On POSIX the file is `chmod 0600` (owner read/write only). Aura's
  Raspberry Pi deployment runs under a dedicated non-root user.
- Home Assistant long-lived tokens, ESP32 MAC keys, and any cloud
  credentials (Google Home, Alexa) are loaded from `.env.agents`
  at runtime.

### Secret scanning

- The OASIS AI wizard ships `scripts/scan_secrets.py`, which runs over
  the working tree + git history. Detects 18+ credential shapes.
- A hardened `.gitignore` blocks `*.env*`, `*_token.txt`,
  `credentials.json`, `*.pem`, `*.key`, SSH keys, and MCP config
  files.

### Physical-device safety controls

This is Aura-specific and load-bearing:

- **Approval gate for physical devices.** Aura's
  `AURA_APPROVAL_FOR_PHYSICAL_DEVICES` flag defaults to **true**. With
  it set, every action that targets a lock, camera, alarm, garage door,
  or comparable device requires an explicit human approval before
  execution — no exceptions, no batching, no "approve all" shortcut.
- **On-device mode by default.** Aura's `AURA_LLM_LOCATION` defaults to
  `on-device` — voice transcription and intent classification run
  locally on the Pi via Whisper.cpp / llama.cpp. Cloud inference is
  an opt-in.
- **Audit log for every physical-device action.** Append-only to
  `data/aura/device_actions.log`. Cannot be disabled from within the
  agent itself.
- **Guest-mode lockout.** When a guest voice profile is detected or a
  guest schedule is active, Aura refuses to trigger locks and cameras
  regardless of approval setting.

### Safety hooks

- `.claude/settings.local.json` registers hooks that block destructive
  shell commands and block any edit that would touch a `.env*` file.
- The Raspberry Pi deployment runs Aura under a dedicated user account
  with no sudo rights. Systemd unit file restricts the process from
  modifying `/etc/`, `/var/`, or other users' home directories.

## Scope for this Agent (Aura / Life-Home)

Aura is the **life, home, and ambient** agent of the C-Suite. By design
it can:

- Read Home Assistant entity state (temperature, motion sensors,
  presence detection, energy use)
- Trigger non-critical devices (lights, music, thermostats) without
  approval when `AURA_APPROVAL_FOR_PHYSICAL_DEVICES` is false (off by
  default for a reason)
- Trigger **critical** devices (locks, cameras, alarms, garage, gates)
  only with explicit per-action approval — **hard rule**
- Maintain a local habits + routines database (wake time, sleep time,
  activity patterns)
- Listen for wake-word and handle voice interactions when
  `AURA_VOICE_ENABLED` is true
- Publish aggregate pulse metrics to `data/pulse/aura_pulse.json`

Aura **cannot**, by policy:

- Bypass the physical-device approval flag under any circumstance.
  Even the owner cannot "temporarily disable" it without editing the
  `.env.agents` file directly (which leaves an audit trail).
- Access financial data (Atlas), publish content (Maven), or send
  outbound business communications (Bravo via `send_gateway`)
- Record or store audio beyond the immediate wake-word buffer.
  Transcripts are discarded unless the user explicitly saved a note.
- Transmit video from connected cameras. Aura can query status; it
  cannot stream video to any cloud service.

## Out of Scope

This policy covers Aura's own code and install path. It does **not**
cover:

- Home Assistant's own security model (entity permissions, user ACLs)
- Vulnerabilities in connected third-party devices (smart locks,
  cameras, ESP32 firmware, etc.)
- The user's home network security (Wi-Fi passwords, router firmware)
- The user's physical-access controls (who else lives in the house)
- Vulnerabilities in upstream dependencies — tracked via GitHub
  Dependabot and patched in regular releases

## Coordinated Disclosure

Please give us a reasonable window to fix before public disclosure.
90 days is the default. **Physical-device safety issues get an
accelerated track — please report these directly to
security@oasisai.work with [AURA-SAFETY] in the subject line** and we
will ship a fix as fast as possible, usually within 48 hours.

Thank you for helping keep our agents safe for the businesses and
households that depend on them.
