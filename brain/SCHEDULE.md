# CC's Daily Schedule — Unified View

> **Purpose:** The single source of truth for CC's day, merged across every agent that touches it. Bravo owns work-block semantics. AURA owns scene/environment. Atlas reads work hours for spend pacing. Maven reads creative windows.
>
> **Rule:** If these sources ever disagree, **this file is the reconciliation**. Edit here first, then sync to Bravo's `brain/DAILY_SCHEDULE.md` and AURA's automation YAMLs.
>
> **Last reconciled:** 2026-04-19 (content-shoot move to 9–11 AM)

---

## Where This Schedule Lives (and who reads it)

| File | Owner | What It Holds | Read By |
|------|-------|---------------|---------|
| `C:\Users\User\Business-Empire-Agent\brain\DAILY_SCHEDULE.md` | Bravo | Work-block semantics, cron jobs, Telegram briefings | Bravo, CC |
| `C:\Users\User\AURA\data\pulse\aura_pulse.json` → `residents.cc.schedule_today` | AURA | Today's concrete times (wake, gym, deep_work, content_shoot, wind_down) | Bravo, Atlas, Maven |
| `C:\Users\User\AURA\home-assistant\automations\scheduled_content_reminder.yaml` | AURA | Time-triggered content check-in | HA |
| `C:\Users\User\AURA\home-assistant\automations\routine_morning_weekday.yaml` | AURA | Lights/music for 7:30 AM wake | HA |
| `C:\Users\User\AURA\home-assistant\automations\routine_evening_wind_down.yaml` | AURA | Wind-down sequence | HA |
| **This file** | AURA (reconciled) | The merged view | CC (human) |

---

## The Week — Weekday Default (Mon–Fri)

| Time | Block | Owner/Scene | Who Triggers |
|------|-------|-------------|--------------|
| 06:30 | Wake + prime (water, no phone 10 min) | AURA `routine_morning_weekday` | HA schedule |
| 07:00 | Movement (gym / run / walk — 60 min) | — | CC |
| 08:00 | Shower + breakfast + light email (45 min) | — | CC |
| 08:45 | Break / coffee / reset (15 min) | — | CC |
| **09:00** | **CONTENT CREATION — record (2h)** 🎬 | **AURA Studio Mode auto-engages** | **HA schedule ← CHANGED** |
| 11:00 | Break + transfer clips to `media/raw/` (15 min) | — | CC |
| 11:15 | DEEP WORK #1 — OUTREACH + SALES (90 min) | AURA Focus Mode | Voice cmd or schedule |
| 12:45 | Lunch + personal (60 min) | — | CC |
| 13:45 | DEEP WORK #2 — CLIENT DELIVERY / BUILD (2h) | AURA Focus Mode (continues) | Voice cmd |
| 15:45 | Break (15 min) | — | CC |
| 16:00 | Learning + strategy (60 min) | — | CC |
| 17:00 | Admin + inbox cleanup (30 min) | — | CC |
| 17:30 | FREE TIME / DJ practice / social | — | CC |
| 22:00 | Wind-down ramp begins (dim lights) | AURA `routine_evening_wind_down` | HA schedule |
| 22:00 | Bravo evening check-in (Telegram) | Bravo | Bravo cron |
| 23:00 | Sleep-window starts — no-nudge | AURA enforced | All agents |
| 00:00 | Target sleep | — | CC |

**Key change today:** Content moved from **11:15 AM → 9:00 AM**. Rationale in [memory/PATTERNS.md](memory/PATTERNS.md): content-after-deep-work = cognitive residue flattens the shoot. Shooting first, working second, protects both.

---

## The Week — Weekend

| Day | Shape |
|-----|-------|
| **Saturday** | Wake 08–09. 1h batch content/review in AM (optional). Rest of day is yours — gym, DJ, social, life. **No outreach.** |
| **Sunday** | Wake 08–09. Morning: Bravo `/briefing`, review week. Afternoon: light building if inspired. **18:00: AURA weekly reflection (voice).** 20:00: Bravo week-ahead prep. |

---

## Weekly Rituals

| When | What | Who Drives |
|------|------|------------|
| Mon 07:00 | Morning briefing (MRR, pipeline, priorities) | Bravo → Telegram |
| Mon 10:00 | Grade Q2 OKRs | CC + Bravo dashboard |
| **Wed 09:00** | **Content batch day (record 2–3 videos at once)** | AURA Studio Mode extended block |
| Fri 16:30 | Weekly retro — what worked, what didn't | Bravo `/retro` |
| **Sun 18:00** | **Weekly reflection (3 wins / 1 lesson / 1 adjustment)** | AURA voice — new |
| Sun 20:00 | Week-ahead plan | Bravo Telegram |

---

## The Three Tiers of Accountability

### Who holds what

- **Bravo holds revenue accountability.** Morning briefing, evening check-in, outreach cadence, deal pipeline.
- **AURA holds life accountability.** Wake time, gym, sleep, content cadence, reflection.
- **Atlas reads both.** Spend-pacing aligns to revenue velocity (Bravo) + lifestyle patterns (AURA).
- **Maven uses AURA's creative windows** to time shoots/posts — will respect the new 9–11 AM content block.

### The Pact (unchanged from Bravo's doc)

CC builds the empire. Bravo runs the machine. Neither works without the other.
AURA runs the environment. Neither works without the space.
The schedule is the minimum. On fire days, CC blows past it. On hard days, the minimum is enough.

---

## What Changed Today (2026-04-19)

| Field | Was | Now | Why |
|-------|-----|-----|-----|
| Content creation window | 11:15–12:15 | **09:00–11:00** | Pre-deep-work shoot preserves shoot energy (LIFE_CANON #4 attention residue) |
| Outreach + sales | 08:00–09:30 | 11:15–12:45 | Shifted right to make room — still 90 min, still protected |
| Client delivery | 09:45–11:15 | 13:45–15:45 | Merged with former Build block — 2h continuous |
| Build (was 13:15–15:15) | Merged | (see above) | One 2h afternoon block replaces two 90-min blocks |
| Content reminder nudge | 14:00 | **09:00** (fire-to-engage) + **10:45** (soft wrap-up) | Becomes a *start* prompt, not a *did-you?* prompt |

---

## What AURA Is Wiring Up Tonight

1. `home-assistant/automations/scheduled_content_reminder.yaml` — trigger time moves from `14:00:00` → `09:00:00` + logic flips from "did you record?" to "Studio Mode starting now, you good to roll?"
2. `data/pulse/aura_pulse.json → residents.cc.schedule_today.content_shoot` — populated daily at boot with today's 09:00–11:00 window so Bravo/Maven see it.
3. Triple-clap still fires Studio Mode manually; no change.

## What Bravo Needs to Update (cross-agent ask)

- [ ] `brain/DAILY_SCHEDULE.md` — swap the 8:00 / 9:30 / 11:15 blocks to match above
- [ ] Telegram morning briefing template — mention "09:00 content block" as today's anchor
- [ ] `/retro` workflow — add "did the 9 AM content block ship?" as a weekly check

> **Sovereignty note:** AURA does NOT edit Bravo's files directly (per self-improvement-protocol guardrail #4). This section is a request — CC or Bravo applies it next session.

---

## Related

- [brain/LIFE_CANON.md](LIFE_CANON.md) — behavioral-science sources backing this schedule (especially #1, #3, #4, #6)
- [memory/PATTERNS.md](../memory/PATTERNS.md) — the 3-hour deep-work pattern this schedule protects
- [personal/USER.md](../personal/USER.md) — CC's goal targets (gym 4/wk, content 5/wk, sleep 7.5h)
- `C:\Users\User\Business-Empire-Agent\brain\DAILY_SCHEDULE.md` — Bravo's canonical work-block doc
