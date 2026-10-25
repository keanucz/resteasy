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
| head on / off | DS18B20 warmth + DHT11 humidity in the pillow | slow (seconds to minutes); fine for the 10 s `bed_exit` rule |
| someone by the bed | HC-SR04 ultrasonic aimed at the floor → `room_motion` | replaces the PIR the contract assumed |
| restlessness | MPU6050 → `motion` | |
| "I'm fine" | hit sensor tap → `keys.fine` | the only key on Mum's pillow |
| talk | laptop mic (Waveshare voice unit in the pillow in progress) | no talk / family keys on the pillow |
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

- **FINE**: "Glad you're OK." → back to `UP`, timer restarts. **Every** no-return runs a new
  check-in, so she is always asked and warned before family are alarmed. After the 2nd "fine" on
  one trip, family get an informational heads-up, not an alarm (provisional, to decide: PR #21).
- **CONFUSED**: gentle reorienting ("It's night, you're at home, the light's on by the bed") → ask again.
- **DISTRESS** → `ESCALATING` at once. Silence / unclear after 3 asks → a warning with 15 s to say
  "I'm fine" → `ESCALATING`, with the reason in one plain sentence for the family.

Claude also writes the spoken lines and the family message. It never decides timers or who to call.

## 4. Family Liaison ladder (least intrusive first)

1. App alert to **every** contact at once ("Check on Mum": push notification + in-app incident).
   Wait 2 min.
2. SMS to contact 1. Wait 2 min.
3. Phone call to contact 1. Wait 2 min.
4. Repeat from step 2 with the next contact.

Contacts go in `resident_contacts.priority` order, but those who are reachable (`on_call` and
outside their own quiet hours) move ahead of those who aren't. Nobody is dropped: if nobody is
reachable, everyone is still tried. Any contact's "I'm on it" in the app
(`POST /api/pillows/{id}/ack`) stops the ladder, and Mum hears "<name> knows, and is checking on
you." There is no second pillow: the adult child only has the app.

**Never auto-calls 911**; the message tells the contact to call if they can't reach her.

## 5. Guardian (plain code, checks every tool call before it is queued)

- Caps: brightness ≤ 40 % at night, volume cap, pulse within 4–14 bpm.
- Max alerts per night per contact; no repeats inside the step wait.
- No medical claims or diagnoses in any message ("may have had a stroke" → blocked and rewritten).
- No raw audio stored; transcripts only.
- **Demo moment:** Claude drafts "she might have had a stroke"; Guardian blocks it on screen and the
  family gets "Mum got up 25 min ago, hasn't come back to bed and didn't answer."

Every decision goes to `agent_log` with `{ts, agent, intent, tool, args, guardian: allowed|blocked, reason}`.

## 6. Family agents + pillow coordinator (Fetch.ai: uAgents on Agentverse, used through ASI:One)

One agent per family member plus one coordinator for the pillow, all mailbox agents on Agentverse
(`agents/fetch/README.md`). Each family member talks to their own agent in ASI:One: "How was Mum's
night?" (a card), "Send Mum a goodnight" (a form card), and goals like "I'm in Denver Thu-Sun, make
sure Mum's covered", which Claude turns into a plan (away nights, goodnights, settings) shown as a
Confirm / Cancel card. Nothing changes before they confirm; plain code then runs the steps through the
API and its Guardian. Every evening (21:00 her time, or "plan tonight") the coordinator asks every
family agent in parallel who can be called first tonight and sets `contacts.on_call` through
`PUT /api/pillows/{id}/roster/{contact}` (Guardian: the last on-call contact stays on). Night Watch
only uses `on_call` for the ORDER of the ladder, so agents can make help come sooner, never later.
The backend never calls the agents; with them off, everything above section 6 is unchanged.

## 7. Stretch: Settle

`restless` while `IN_BED` → breathing `pulse` 12 → 6 bpm for 10 min, optional story or music on
request; checks that `motion` drops.

## Sponsor targets

| Tier | Sponsor | Where |
|---|---|---|
| Core | Anthropic | Claude tool loop + Guardian ("knows where it could go wrong") |
| Core | Cartesia | check-in voice, goodnight playback |
| Core | Microsoft "Built for the Real World" | healthcare framing, measurable (time on the floor), responsible design |
| Bet | Fetch.ai | family agent in ASI:One |
| Dropped | Atlassian (must be a Forge app for Jira/Confluence), Moss and ElevenLabs (second voice stack), Backboard, Spacetime and Convex (backend is Supabase, not a sponsor), MLH Tiger Data (only if night history moved there) | |

## Build order

1. Event deriver + Night Watch against `sim/pillow_sim.py --scenario no_return`.
2. Check-in: Cartesia voice + Claude classify.
3. Guardian + ladder: in-app alert first, then SMS.
4. `agent_log` live in the family app.
5. Fetch family agent. 6. Settle.

## Needs from other lanes

- **Szymon:** Supabase tables for pillow state, events, commands, `agent_log`, contacts (with phone
  numbers) and config; owner of the schema. Agent code lives in the backend under `app/agents/`.
- **Keanu / Adyan:** `keys.fine` from the hit sensor on Mum's pillow; path light and motor on Mum's pillow.
