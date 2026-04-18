# ROOMMATE AGENT PROTOCOL

> **Purpose:** The formal contract for how a second resident's AI agent (e.g., Adon's AIOS stack) hooks into Aura without exposing the other resident's private data.
> **Audience:** Adon, and any future roommate who brings their own agent(s) into the apartment.
> **Last updated:** 2026-04-18

---

## 1. The Core Principle

**Aura is the household's Life/Home agent. It serves every resident.** Each resident owns their own private slice of Aura's state and decides what to share with the apartment at large — and what to share across the resident boundary with the *other* resident's agents.

Three data classes, three privacy rules:

| Data Class | Location in `aura_pulse.json` | Default Visibility |
|------------|-------------------------------|--------------------|
| **Apartment-shared** | `apartment_shared.*` | Every agent — CC's and Adon's |
| **CC's private** | `residents.cc.*` | CC's agents only (Bravo, Atlas, Maven, CC-self) |
| **Adon's private** | `residents.adon.*` | Adon's agents only (his AIOS stack, Adon-self) |

Any field a resident wants to cross the boundary must be **explicitly opted in** via `adon_shared_fields` or `cc_shared_with_adon_fields`.

---

## 2. What Adon's Agent Hooks Into

### 2a. Read Access

Adon's agents may read from `C:\Users\User\AURA\data\pulse\aura_pulse.json`:
- **Always:** `apartment_shared.*` (lights, music, climate, locks, guest_mode, away_mode, shared_supplies, utilities)
- **Always:** `residents.adon.*` (Adon's own slice — he's reading his own data)
- **Only if opted in:** Any field in `cc_shared_with_adon_fields` from `residents.cc.*`

Adon's agents may **never** read CC's private fields unless CC has opted that specific field into `cc_shared_with_adon_fields`. Same rule mirrors for CC's agents reading Adon.

### 2b. Write Access

Adon's agent writes to its **own** pulse file, which lives in Adon's repo (wherever Adon chooses — e.g., `C:\Users\Adon\AIOS\data\pulse\adon_pulse.json`). Aura then reads that file on session start.

Adon's agent **never** writes directly to `aura_pulse.json`. That would violate sovereignty — the same rule CC's agents follow. Adon's agent tells Aura what it wants to expose by writing its own pulse; Aura mediates and copies/references the chosen fields into `residents.adon.*` on her next write.

### 2c. Registration

When Adon's agent is ready to connect, Aura adds an entry to `adon_agents_connected`:

```json
{
  "adon_agents_connected": [
    {
      "agent_name": "aios_core",
      "repo_path": "C:\\Users\\Adon\\AIOS",
      "pulse_path": "C:\\Users\\Adon\\AIOS\\data\\pulse\\adon_pulse.json",
      "subscribed_apartment_fields": ["lights_state", "music_state", "guest_mode", "climate"],
      "opted_in_shared_from_adon": ["presence"],
      "opted_in_shared_from_cc": [],
      "connected_at": "<ISO-8601 UTC>",
      "last_seen_pulse_age_hours": 0
    }
  ]
}
```

Multiple Adon agents can register. Each one must declare what apartment_shared fields it reads and what personal fields Adon has chosen to expose.

---

## 3. The Opt-In Sharing Contract

### 3a. Adon Shares Into CC's Side

Adon's agent can write an `opted_in_shared_from_adon` list in its registration. Aura copies those field values from its read of `adon_pulse.json` into `residents.adon.*` and also into `adon_shared_fields` so CC's agents know what's crossing the boundary.

Example — Adon shares presence but not habits:
```json
"adon_shared_fields": ["presence"]
```

Now Bravo can see "Adon is home" but not "Adon went to the gym 4 days in a row."

### 3b. CC Shares Into Adon's Side

Same pattern inverted. CC declares via Aura: "share my `schedule_today.content_shoot` so Adon knows when I'm filming." Aura adds `schedule_today.content_shoot` to `cc_shared_with_adon_fields`. Now Adon's agent can read that specific field.

### 3c. Revocation

Either resident may remove a field from their shared list at any time. On Aura's next write, the field is dropped from the shared array and downstream agents lose access. No cached reads — every session re-checks the contract.

---

## 4. Shared Supabase Tagging

If Adon joins the shared Supabase project (`phctllmtsogkovoilwos`), every row his agents write **must** include:

```
agent: 'adon_<agent_name>'
resident: 'adon'
```

CC's agents already tag `resident: 'cc'`. Apartment-level rows (shared lighting state, utility readings, guest mode toggles) tag `resident: 'shared'`.

RLS on `agent_traces` enforces:
- An agent can only INSERT rows with its own `agent` value.
- Rows tagged `resident: 'cc'` are readable only by CC's agents + `resident: 'shared'` rows.
- Rows tagged `resident: 'adon'` are readable only by Adon's agents + `resident: 'shared'` rows.
- Rows tagged `resident: 'shared'` are readable by everyone.

Every cross-resident read (Adon's agent reading a CC-opted-in field, or vice versa) is logged as a row with `action: 'cross_resident_read'` for audit.

---

## 5. Apartment-Level Conflict Resolution

When CC and Adon's preferences collide on **shared** surfaces (ambient music, overhead lighting, thermostat), Aura applies:

1. **Guest mode trumps all.** If guest_mode=true, only the guest-mode scene runs.
2. **Last-one-home wins for ambient settings.** The resident who most recently arrived home sets the default scene.
3. **Private rooms always defer to their occupant.** If Adon is in his room, his room lighting/music respects his preference regardless of who arrived home last.
4. **Sleep protection beats everything except guest mode.** If any resident is in their wind-down → wake window, Aura will not escalate volume, flip lights, or fire nudges in shared areas adjacent to the sleeping room.
5. **CC (or Adon) manual override** at any time, final.

---

## 6. Safeguards Aura Enforces

| Rule | Enforcement |
|------|-------------|
| Never expose CC's habits/sleep/mood/health/spending to Adon's agents without opt-in | `residents.cc.*` filtered on every read; opt-in only via explicit field list |
| Never expose Adon's habits/sleep/mood/health/spending to CC's agents without opt-in | `residents.adon.*` filtered on every read; opt-in only via explicit field list |
| Guest mode pauses personal data collection | All habit trackers and learning engines halt writes while guest_mode=true |
| Cross-resident reads are logged | Supabase `agent_traces` row per read with agent, resident, field, timestamp |
| Sleep window is inviolable | Sibling pulse directives marked CRITICAL bypass; all others are queued until wake |

---

## 7. What Adon's Agent MUST Do to Hook In

Checklist Adon (or Adon's AIOS session) follows:

1. Create his agent's pulse file at `<his-repo>/data/pulse/adon_pulse.json` with at minimum:
   - `agent: '<agent_name>'`
   - `resident: 'adon'`
   - `updated_at: <ISO-8601 UTC>`
   - Any fields he chooses to expose
2. Tell Aura the pulse path (either CC pastes it in, or Adon opens an Aura session and says "register my agent at <path>").
3. Declare his `subscribed_apartment_fields` (what apartment_shared fields his agent cares about).
4. Declare his `opted_in_shared_from_adon` list (what personal fields he's exposing to CC's side, if any).
5. If joining shared Supabase: add his agent name to RLS allowlist, tag every row with `agent: 'adon_<name>'` and `resident: 'adon'`.
6. Respect the write boundary: his agent writes ONLY to `adon_pulse.json` and his own Supabase rows — never to `aura_pulse.json` directly, never to CC's agent files.

Aura confirms the hookup by adding the registration entry to `adon_agents_connected` on her next session and reading his pulse going forward.

---

## 8. What Happens If Adon Leaves or a Future Roommate Moves In

- On move-out: Aura removes the `residents.<name>` slice and all `adon_agents_connected` entries. Supabase rows tagged `resident: 'adon'` are retained for personal export if requested, then purged.
- On move-in of a new roommate: Add a new resident slice under `residents.<new_name>` with `visible_to: ['<new_name>_self', '<new_name>_agents']`. Same contract applies.
- Apartment capacity is the only hard cap; the schema supports N residents.

---

## 9. Related Docs

- `C:\Users\User\Business-Empire-Agent\brain\C_SUITE_ARCHITECTURE.md` — the 4-agent operating model + decision rights
- `C:\Users\User\Business-Empire-Agent\brain\CROSS_AGENT_AWARENESS.md` — pulse protocol + multi-resident privacy summary
- `C:\Users\User\AURA\data\pulse\aura_pulse.json` — the live pulse file this doc governs

---

**Bottom line for Adon:** Plug in by writing your own pulse file at a path of your choosing, then tell Aura where it lives. Declare what you share. Everything else stays yours.
