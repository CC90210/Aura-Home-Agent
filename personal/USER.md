# USER.md — Personal Configuration Overlay

> **Purpose:** This file holds all household-specific and resident-specific config that would change if AURA were cloned into another home. When Business-in-a-Box sells AURA as a Tier 2 upsell or free add-on, `personal/USER.md` is the *only* file a new household needs to fill in.
>
> **Rule:** No file inside `voice-agent/`, `learning/`, or `home-assistant/` should hardcode personal identifiers. They read from here (or from `.env`) and fall back to the keys below.
>
> **Clone-ability:** `git clone <repo> && cp personal/USER.template.md personal/USER.md && fill in` is the entire personalization pass.

---

## Household Identity

```yaml
household_name: "CC + Adon Apartment"
timezone: "America/Toronto"            # Montreal (EST/EDT)
city: "Montreal"
country: "Canada"
install_type: "personal"               # personal | client | demo
install_tier: "pro"                    # lite | standard | pro
```

## Residents

### Primary

```yaml
- id: conaugh
  display_name: "Conaugh"
  preferred_address: "CC"
  aliases: ["CC", "Conaugh", "king", "Con"]
  pronouns: "he/him"
  age: 22
  role: "Full-time AI operator, DJ, content creator"
  phone_entity: "person.conaugh"
  icloud_email: "Konamak@icloud.com"
  voice_signature_trained: false

  speech_tendencies:
    vibes: ["hype", "confident", "direct"]
    slang_seeds: ["yo", "real talk", "bet", "for real", "lock in"]

  goals:
    gym_days_per_week: 4
    content_days_per_week: 5
    sober_streak_target_days: 30
    sleep_hours_target: 7.5
    wake_target_weekday: "07:30"
    wind_down_target: "23:00"

  scenes_most_used: ["studio", "focus", "goodnight"]
```

### Secondary (Roommate)

```yaml
- id: adon
  display_name: "Adon"
  preferred_address: "Adon"
  aliases: ["Adon", "A-D-O-N", "Don"]
  pronouns: "he/him"
  age: 21
  role: "Phone sales, content creator, musician"
  phone_entity: "person.adon"
  voice_signature_trained: false

  privacy_posture: "default_private"     # Opts in via ROOMMATE_AGENT_PROTOCOL
  agent_connected: false                 # Will flip true when AIOS stack registers
```

## Apartment Layout

> **Status: TBD** — final room assignments get filled in after walk-through. Until then, AURA treats `living_room`, `bedroom`, `studio` as abstract logical rooms mapped to HA entities.

```yaml
rooms:
  shared:
    - living_room                        # primary common space
    - kitchen
    - bathroom
  private_cc:
    - bedroom_cc                         # CC's room (private)
    - studio                             # CC's content creation space
  private_adon:
    - bedroom_adon                       # Adon's room (private)
```

## Speakers, Lights, and Scenes (overridable)

These mirror `voice-agent/config.yaml → speakers:` and `home-assistant/scenes/`. Adjust once the Pi is online and entity IDs are finalized.

```yaml
default_speaker: "media_player.living_room_speaker"
bedroom_speaker: "media_player.bedroom_speaker"
studio_speaker: "media_player.studio_speaker"

favorite_playlists:
  cc_morning: "spotify:playlist:TBD"
  cc_studio: "spotify:playlist:TBD"
  cc_dj_practice: "spotify:playlist:TBD"
  cc_workout: "spotify:playlist:TBD"
  shared_dinner: "spotify:playlist:TBD"
```

## Accountability Defaults (CC)

These drive habit_tracker nudges. Respect sleep window 23:00–07:00 (no-nudge) and guest_mode override.

```yaml
tracked_habits_cc:
  - wake_up_on_time
  - gym
  - deep_work
  - healthy_dinner
  - bedtime
  - hydration
  - content_shoot
  - sober_streak

nudge_channels:
  voice: true                            # AURA speaks the nudge via TTS
  dashboard: true                        # shows in dashboard/
  obsidian_daily_note: true              # writes to daily note
```

## What *Never* Lives in This File

- API keys, tokens, PINs → `.env` only (`HA_TOKEN`, `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`, `AURA_VOICE_PIN`, `SPOTIFY_CLIENT_ID`, `GOVEE_API_KEY`)
- Home Assistant entity configuration → HA itself is the source of truth
- Adon's private data → lives in `residents.adon.*` of `aura_pulse.json`, mediated by ROOMMATE_AGENT_PROTOCOL
- Pattern-engine learned preferences → `data/patterns.db`

## Clone-Ability Checklist

When deploying AURA to a new household:

1. Copy `personal/USER.template.md` → `personal/USER.md`
2. Fill in every `TBD` and replace every occurrence of `conaugh`/`adon` with actual resident IDs
3. Rename `residents.cc` and `residents.adon` keys in `data/pulse/aura_pulse.json` seed to match new IDs
4. Update `learning/config.yaml → residents` list
5. Update `voice-agent/personality.yaml → residents` section
6. Regenerate voice-signature profiles (`person_recognition.py --train`)
7. Walk through house, populate `rooms:` with actual room IDs
8. Confirm HA entity IDs match `speakers:` block here

## Related

- `CLAUDE.md` — universal project rules
- `data/pulse/aura_pulse.json` — runtime state (3-part privacy)
- `docs/ROOMMATE_AGENT_PROTOCOL.md` — how second resident's agents hook in
- `brain/LIFE_CANON.md` — behavioral-science foundations that inform every nudge
