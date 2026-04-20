---
name: weekly-reflection
version: 1.0.0
description: "Sunday 18:00 local voice-triggered reflection. Structure: 3 wins / 1 lesson / 1 adjustment. Writes to memory/weekly_reflections.md. Surfaces cross-week patterns and integrates Bravo context when relevant."
metadata:
  category: life-agent
  installs_in: [aura]
  tier: full
  schedule: "Sunday 18:00 America/Toronto"
triggers: [weekly-reflection, sunday-reflection, reflect-on-week, review-my-week, wrap-up-week]
canon_citations:
  - "[LIFE_CANON #1] Clear — identity-based habits, review to reinforce identity"
  - "[LIFE_CANON #7] Ericsson — deliberate practice requires explicit review + feedback"
  - "[LIFE_CANON #8] Kahneman — System 2 override of week-in-review avoids availability bias"
  - "[LIFE_CANON #9] Stoics — weekly retrospective mirrors Seneca's evening review"
---

# Weekly Reflection Skill

Sunday 18:00 local (America/Toronto). AURA opens a short voice conversation with the resident that produces a durable written record of the week.

---

## Why this exists (per LIFE_CANON)

- **Clear (#1):** Habits are votes for an identity. A weekly "did I act like the person I said I'd be?" check converts passive behavior into chosen identity.
- **Ericsson (#7):** Deliberate practice requires explicit review — not just reps. The lesson step forces concrete feedback.
- **Kahneman (#8):** Without a structured prompt, the mind grabs the *vivid* memory (the one argument, the one missed gym day). Structure shifts to System 2 and forces a balanced view.
- **Stoicism (#9):** Seneca wrote in *On Anger* that he examined his day every evening — "what bad habit have you cured? what vice withstood? in what respect are you better?" Weekly reflection is the low-cost ritualized version.

---

## Structure — 3 Wins / 1 Lesson / 1 Adjustment

Fixed template. Never expand. The brevity is the point — if CC can't name three wins, the week was either bad or under-observed, and either answer is signal.

### 3 Wins
What did you do this week that you're proud of? No size gate — "I went to the gym Monday" counts equally with "I closed a client." Identity-reinforcing, not achievement-gated.

### 1 Lesson
What did this week teach you? Something you now believe that you didn't a week ago. Must be specific and actionable, not a platitude. Prompt: "what would past-you have been surprised to learn?"

### 1 Adjustment
What is one concrete thing — single, small, measurable — you're changing next week? Not a vague aspiration ("sleep more") but a mechanism ("lights dim at 22:30 on weeknights").

That's it. 5 minutes of talking. AURA transcribes, structures, and writes.

---

## Voice Flow

```
18:00 Sunday local → AURA checks:
  1. Is CC home? (residents.cc.presence.home)
  2. Is guest_mode or sleep_window active? If yes, defer.
  3. Did we already run this week? (check last entry in memory/weekly_reflections.md)

If clear to proceed:

AURA:  "Yo CC — Sunday wrap. Three wins, one lesson, one adjustment. You ready?"

CC:    [yes / later / skip]

If "later" → reschedule for Monday 09:00 or explicit next-time.
If "skip"  → log skip with reason prompt; surface in monthly report.

AURA:  "Three wins. What went right this week?"
CC:    [speaks wins — STT captures]
AURA:  [brief ack — "that's solid" — never evaluate] "One lesson. What do you know now you didn't Monday?"
CC:    [speaks lesson]
AURA:  "One adjustment for next week."
CC:    [speaks adjustment]
AURA:  [writes to memory/weekly_reflections.md]
       [checks for cross-week patterns — see below]
       "Logged. If the adjustment needs a scene tweak or a scheduled nudge, tell me."
```

Total turns: 4. Total time: target < 5 min.

---

## Cross-Week Pattern Detection

After every write, AURA scans the last 4 weeks for:

### Habit-streak-broken patterns
- Example: "gym streak broken 3 Wednesdays in a row" → surface: *"Quick flag — you've missed Wed gym three weeks running. What's the pattern there?"*
- Detection: streak field in habit_log keyed to day-of-week.

### Recurring-lesson patterns
- Same keyword or theme appearing in the "lesson" slot 2+ weeks running.
- Example: two weeks mention "deep work" in lesson → *"'Deep work' keeps showing up in your lessons. Two weeks now. Want me to make the Focus scene auto-trigger Mon/Wed/Fri 9-11?"*

### Adjustment-never-shipped patterns
- An adjustment from week N that wasn't reflected in behavior by week N+2 → AURA names it directly: *"You said 'lights out by 11:30' two Sundays ago. Pi logs say 00:47 average since. Still the right move, or was the adjustment wrong?"*
- No shaming — treat as data quality question, not moral failing.

### Bravo-context integration
If Bravo's pulse shows a deal closed or a funnel launched this week, AURA asks the win question with context:
- *"Bravo logged a close on Wed. Did that feel like a win to you, or was the grind heavier than the win landed?"*
- *"PULSE funnel went live Monday. Reflect on the shipping, not just the outcome."*

If Atlas flagged lean-week, AURA suppresses any win-related takeout/reward-purchase framing.

---

## Output Format (memory/weekly_reflections.md)

Append-only markdown. Each week = one H2 block.

```markdown
## Week of 2026-04-12 → 2026-04-18 — conaugh

**3 Wins**
- Shipped dashboard auth
- Hit gym 4 days
- Closed first PULSE call

**1 Lesson**
Content shoots after deep-work blocks land flat — the cognitive residue costs the shoot energy.

**1 Adjustment**
Shoots move to pre-deep-work slots (9-11am) starting Monday 2026-04-20.

**Canon:** [#1 environment], [#4 deep work ritual], [#8 attention residue]

**Cross-week patterns detected:** none

**Bravo context:** PULSE funnel launch, Bennett concentration 94%.

---
```

The machine-readable mirror stays in `memory/weekly_reflections.json` (existing file) — the markdown is for humans + Obsidian.

---

## Scheduling

AURA's cron trigger:
- `0 18 * * 0` local (Sunday 18:00 America/Toronto)
- Pre-check: guest_mode off, sleep_window off, resident home
- If precondition fails, retry at 18:30, 19:00, 20:00. Max 3 retries, then log skip and defer to next Sunday.

Manual invocation:
- Voice: "Hey Aura, let's do the weekly reflection" → any time
- Dashboard button: "Weekly reflection now"

---

## Rules

1. **Never expand the template.** Three wins, one lesson, one adjustment. More fields = lower completion rate.
2. **Never evaluate the resident's wins.** Acknowledge, don't score.
3. **Never compare to Adon.** Same rule as the rest of AURA — per-resident only.
4. **Surface patterns neutrally** — as data questions, not judgments.
5. **Respect sleep window.** If 18:00 lands inside a wind-down window (rare for Sunday), defer to next available slot outside the window.
6. **Guest-mode override.** If guests present, skip silently.
7. **If Pi offline** — skill writes a stub entry noting "reflection deferred — hardware offline" so the gap shows in the monthly report.

---

## Metrics (Protocol 2 — self-optimize)

- **Completion rate:** % of Sundays where a full reflection was captured (target > 70%)
- **Avg words per section:** signal of engagement (< 5 words/section = template collapsing to placeholder)
- **Pattern-surface acceptance rate:** when AURA surfaces a cross-week pattern, does CC engage or deflect? Engagement = pattern was well-timed.
- **Adjustment-ship rate:** did week N's adjustment appear in week N+1 data? Low rate = adjustments are aspirational, not operational.

All logged to `skill_activation` table when Supabase is live.

---

## Related

- `brain/LIFE_CANON.md` — behavioral-science basis
- `voice-agent/weekly_reflection.py` — the runtime implementation
- `memory/weekly_reflections.md` — the human-readable log (this skill appends here)
- `memory/weekly_reflections.json` — the machine-readable mirror (existing)
- `scripts/aura_analytics.py` — monthly exporter reads reflections and surfaces them in the monthly brief
- `skills/self-improvement-protocol/SKILL.md` — the meta-loop this skill feeds into
