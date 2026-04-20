# USER.template.md — Personal Configuration Template

> Copy this file to `personal/USER.md` and fill in for your household.
> See `docs/CLIENT_ONBOARDING.md` for the full install walkthrough.

---

## Household Identity

```yaml
household_name: "TBD"
timezone: "America/Toronto"
city: "TBD"
country: "TBD"
install_type: "client"                  # personal | client | demo
install_tier: "lite"                    # lite | standard | pro
```

## Residents

```yaml
- id: resident_1
  display_name: "TBD"
  preferred_address: "TBD"
  aliases: []
  pronouns: "TBD"
  age: null
  role: "TBD"
  phone_entity: "person.resident_1"
  voice_signature_trained: false

  speech_tendencies:
    vibes: []
    slang_seeds: []

  goals:
    gym_days_per_week: 3
    sleep_hours_target: 7.5
    wake_target_weekday: "07:00"
    wind_down_target: "23:00"

  scenes_most_used: []
```

Add a second `- id:` block per additional resident, each governed by the ROOMMATE_AGENT_PROTOCOL privacy contract.

## Apartment Layout

```yaml
rooms:
  shared: []
  private_resident_1: []
```

## Speakers & Playlists

```yaml
default_speaker: "media_player.TBD"
favorite_playlists: {}
```

## Tracked Habits

```yaml
tracked_habits_resident_1: []
```

## Environment Variables (.env)

Do NOT put these in this file. Put them in `.env` at project root:

```
HA_URL=http://homeassistant.local:8123
HA_TOKEN=
ANTHROPIC_API_KEY=
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=
AURA_VOICE_PIN=
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
GOVEE_API_KEY=
```
