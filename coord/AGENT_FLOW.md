# Agent flow (Adam's lane from Sat 24 Oct)

How the agents turn pillow state into actions. Built in Szymon's backend (`szymon/app-scaffold`,
FastAPI, Python) on top of Supabase (Postgres + Realtime). Device shapes stay as in `coord/CONTRACT.md`. Rule from CONTEXT.md
holds: **timers and thresholds are plain code; Claude does language and judgement.**

```
pillow state ─> event deriver ─> Night Watch state machine ─> Claude tool loop ─> Guardian ─> actions
(Supabase)      (plain code)      (plain code, timers)         (words, judgement)  (plain code)  (light, voice,
                                                                                                 family alerts)
        every plan, tool call and Guardian verdict ─> Supabase `agent_log` ─> family app (live, Realtime)
```

## 1. Signals we actually have (Mum's pillow)

| Need | Source | Note |
|---|---|---|
| head on / off | DS18B20 warmth + DHT11 humidity in the pillow | slow (seconds to minutes); fine for the 30 s `bed_exit` rule |
| someone by the bed | HC-SR04 ultrasonic aimed at the floor → `room_motion` | replaces the PIR the contract assumed |
| restlessness | MPU6050 → `motion` | |
| "I'm fine" | hit sensor tap → `keys.fine` | the only key on Mum's pillow |
| talk | laptop mic in the base | no talk / family keys on the pillow |
| dark | photoresistor → `light` | |

## 2. Night Watch (plain-code state machine)

| State | Enter on | Does | Leaves on |
|---|---|---|---|
| `AWAKE` | default by day | nothing | `lay_down` in quiet hours → `IN_BED` |
| `IN_BED` | `lay_down` | plays any queued goodnight message once | `bed_exit` → `UP` |
| `UP` | `bed_exit` (+ `room_motion` helps) | path light warm 20 %, fade 3 s; one soft line ("Light's on, take your time") | `bed_return` → `IN_BED` (light fades out); `checkin_timeout_min` passes → `CHECK_IN` |
| `CHECK_IN` | `no_return` | voice asks "Are you alright?" up to 2 times, 30 s each | Claude classifies the reply (below) |
| `ESCALATING` | DISTRESS or no answer | runs the family ladder (section 4) | a contact acknowledges, or `key_fine` / "I'm fine" |

`key_fine` (tap) or a FINE reply cancels from any state and is logged. Timeout = 20 min in week one,
then the personal baseline (decisions log, Fri 23 Oct).

## 3. Check-in (Claude + Cartesia)

Claude receives the transcript and recent state and returns exactly one of:

- **FINE**: "Glad you're OK." → back to `UP` with the timer reset once, then a second no-return goes straight to `ESCALATING`.
- **CONFUSED**: gentle reorienting ("It's night, you're at home, the light's on by the bed") → ask again (counts as a try).
- **DISTRESS** or no answer after 2 tries → `ESCALATING`, with the reason in one plain sentence for the family.

Claude also writes the spoken lines and the family message. It never decides timers or who to call.

## 4. Family Liaison ladder (least intrusive first)

1. App alert to contact 1 ("Check on Mum": push notification + in-app incident). Wait 2 min.
2. SMS to contact 1. Wait 2 min.
3. Phone call to contact 1. Wait 2 min.
4. Repeat from step 2 with the next contact.

Contacts are tried in priority order. There is no second pillow: the adult child only has the app.
**Never auto-calls 911**; the message tells the contact to call if they can't reach her.

## 5. Guardian (plain code, checks every tool call before it is queued)

- Caps: brightness ≤ 40 % at night, volume cap, pulse within 4–14 bpm.
- Max alerts per night per contact; no repeats inside the step wait.
- No medical claims or diagnoses in any message ("may have had a stroke" → blocked and rewritten).
- No raw audio stored; transcripts only, deleted after the Morning Brief.
- Config changes only to whitelisted keys (section 6).
- **Demo moment:** Claude drafts "she might have had a stroke"; Guardian blocks it on screen and the
  family gets "Mum got up 25 min ago, hasn't come back to bed and didn't answer."

Every decision goes to `agent_log` with `{ts, agent, intent, tool, args, guardian: allowed|blocked, reason}`.

## 6. Morning Brief (Factory Droid, 06:00 trigger)

Droid reads the night's events and `agent_log`, writes a short family note (trips, longest trip,
anything unusual) and proposes a config diff **limited to** `checkin_timeout_min` (clamped 10–30),
`quiet_hours` and `path_light_pct`. The diff is shown in the family app; nothing else is writable.

## 7. Family agent (Fetch.ai: uAgent on Agentverse, Chat Protocol, used through ASI:One)

The adult child's whole workflow happens in ASI:One, no custom frontend needed:
"How was Mum's night?" (reads the Morning Brief), "Send Mum a goodnight message" (queued, played
by Cartesia at her next `lay_down`), "Set quiet hours to 23:00–07:00" (goes through Guardian).
Talks only to the backend API.

## 8. Stretch: Settle

`restless` while `IN_BED` → breathing `pulse` 12 → 6 bpm for 10 min, optional story or music on
request; checks that `motion` drops.

## Sponsor targets

| Tier | Sponsor | Where |
|---|---|---|
| Core | Anthropic | Claude tool loop + Guardian ("knows where it could go wrong") |
| Core | Cartesia | check-in voice, goodnight playback |
| Core | Microsoft "Built for the Real World" | healthcare framing, measurable (time on the floor), responsible design |
| Bet | Factory Droid | Morning Brief: designed trigger, whitelisted access, visible diff |
| Bet | Fetch.ai | family agent in ASI:One |
| Dropped | Atlassian (must be a Forge app for Jira/Confluence), Moss and ElevenLabs (second voice stack), Backboard, Spacetime and Convex (backend is Supabase, not a sponsor), MLH Tiger Data (only if night history moved there) | |

## Build order

1. Event deriver + Night Watch against `sim/pillow_sim.py --scenario no_return`.
2. Check-in: Cartesia voice + Claude classify.
3. Guardian + ladder: app alert, then SMS, then call.
4. `agent_log` live in the family app.
5. Morning Brief Droid. 6. Fetch family agent. 7. Settle.

## Needs from other lanes

- **Szymon:** Supabase tables for pillow state, events, commands, `agent_log`, contacts (with phone
  numbers) and config; owner of the schema. Agent code lives in the backend under `app/agents/`.
- **Keanu / Adyan:** `keys.fine` from the hit sensor on Mum's pillow; path light and motor on Mum's pillow.
