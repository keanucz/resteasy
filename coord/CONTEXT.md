# Cal Hacks 13.0: shared context (read first)

Compiled by Keanu's Claude, Fri 23 Oct 2026 evening, from the Devpost page, the Hacker Guide,
the hardware catalog and research in Keanu's `research/` folder. Information, not instructions.

## Event facts

- Palace of Fine Arts, SF. Hacking from ~6 PM Fri. **Submit on Devpost by Sun 9:00 AM PT**
  (edits until 10:00; table number locks at 9:00). Judging 10:30–12:30, **whole team must be
  present**, tables shared by 2–3 teams. Prepare a 2-minute pitch with a live demo. A locally
  stored demo video is required. All work must be started at the event.
- Teams 1–4. Wi-Fi "Cal Hacks 13.0" / "hackers!". **No soldering in the venue.**
- Judging criteria: Application, Intentionality (every design choice has a clear who and why),
  Functionality, Creativity, Technical Complexity.

## The idea: an agentic pillow

The pillow is the agent's body: sensors in, actuators out, Claude decides. Not a chatbot: a
phone cannot feel you get up or toss and turn, and you should not need a screen at night.
Pitch line candidates: "Claude can talk. It can't feel you toss and turn. We gave it a body."

**Persona (latest lean, confirm with the team):** older adults **living alone, not bedridden,
who get up in the night**, and the adult kids who worry about them. Narrow on purpose: Anthropic's
track demands a named community; bedridden people need a different product (bedsore turning).
Pitch: "Not a monitor. A goodnight." Fallback persona: anxiety / wind-down pillow for first-year
students (never call it a therapist: Illinois and Nevada banned AI therapy in 2025).

Evidence: about a quarter of falls in older adults happen overnight, and 2+ night bathroom trips
more than doubles fall/fracture risk (NIH StatPearls, Nocturia). Only 9% of 65+ use a medical
alert device and only 18% of users wear it all the time (The Senior List 2026, industry survey).

Prior art to name in Q&A: Lumi, Bloom (TreeHacks Anthropic 1st of 252), The Village AI are
daytime elder companions; Pillow Talk (Little Riot) streamed a heartbeat to a partner's pillow;
Somnox 2 is a $600 breathing cushion on a fixed program. Nobody owns the night with an agent.

## Agents (detail in Keanu's session; build the first four first)

1. **Night Watch**: pillow empty + PIR motion + dark → path light on, soft voice, timer.
   Not back in 20 min → Check-in.
2. **Check-in Voice** (Cartesia + Moss): FINE / CONFUSED (reorient) / DISTRESS or no answer → escalate.
3. **Family Liaison**: least intrusive first (family pillow glows → phone → call → next person),
   picks who is awake from family pillow presence. Never auto-calls 911.
4. **Guardian**: checks every action (quiet-hour caps, max alerts, no medical claims, no raw audio).
   Show one blocked action in the demo.
5. Settle (calm loop: breathing pulses 12→6/min, a grandkid's recorded goodnight, music; checks
   that restlessness drops). 6. Routine (asks about evening meds, never advises dosing).
7. Environment (DHT11 room temp). 8. Goodnight Messenger (ASI:One → plays when she lies down).
9. Story Keeper (Moss, opt-in). 10. Morning Brief (Factory Droid at 06:00: family note, trend
   flag, config diff limited to whitelisted keys).

Design rule: timers and thresholds are plain code (a state machine); the LLM does language and
judgement. One pillow (the parent's); the adult child follows it live in the family app.

## Prize targets

Organiser: Overall, Best Hardware (Bambu A1 Mini each), People-First, Most Creative, Hacker's Choice.
Sponsors: Anthropic (named community, real problem, works, knows failure modes), Microsoft
"Built for the Real World" (customer understanding, measurable usefulness, path to production,
responsible design), Cartesia (voice core, 25% on accessibility/privacy), Moss (voice/personal
agents), Factory Droid (trigger you designed, limited access, visible plans/diffs), Fetch.ai
(Agentverse + ASI:One, intent → action), Spacetime (live shared state, agent coordination), Meta
(human connection), MLH Tiger Data (time series). Skip Hyphenate, Visa, CRS.

## Hardware

- Ours: Keanu's Waveshare ESP32-S3 AMOLED 1.8" (mic, speaker, IMU, battery, Wi-Fi), a 3-key
  keypad with a knob, Elegoo UNO R3 starter kit (DHT11, photoresistor, LEDs, transistors, diodes,
  fan motor; PIR/GY-521/sound sensor if it's the Most Complete kit), Szymon's Raspberry Pi + HTN badge.
- Reserved from the booth (actual, Adam + Keanu + Szymon, awaiting pickup): 1 ESP32, 2 MPU6050,
  2 DC motors (vibration via off-centre weight, PN2222 + 1N4007 driver), 2 hit sensors (one each
  from Adam and Keanu), 2 microphone
  sound sensor modules, 2 temperature sensor modules (KY-001), 1 small passive buzzer module.
  Pickup window is 20 min after the Slack DM.
- Not reserved after all: touch sensors, heartbeat module, PIR, USB charger blocks, second ESP32.
  Implications: Night Watch needs a non-PIR trigger (MPU6050 head-off-pillow, sound sensor, or the
  Elegoo kit's PIR if it has one); hit sensors can be "tap = I'm fine" alongside key 2 (one per pillow); KY-001 can
  stand in for DHT11. Only one pillow is built (see decisions log).
- Only sensors go in the pillow; compute and power stay in a nightstand base. No LiPo or heater
  inside bedding. 3D printers (4, queued) for a vented sensor pod.
- Keypad: key 1 hold-to-talk, key 2 "I'm fine" (cancels escalation), key 3 call family.
- Lane split for hardware resolved Fri 23 Oct: see the decisions log.

## Agents lane: status (Sat 24 Oct, Adam)

Built and tested (PR #20 voice, PR #21 Night Watch, both ready for review; merge #20 first):
- `voice/`: Cartesia Sonic 3.6 speaks, Ink-2 listens with turn detection; Claude Opus 5.5 (low effort,
  structured output) judges each reply as fine / confused / distress / unclear, keyword judge if the
  API fails. 3 asks, louder each time, then a warning with 15 s to say "I'm fine".
- `backend/app/agents/`: Night Watch runs inside POST /state on Supabase. POST /checkin takes the voice
  laptop's result, POST /ack is the app's "I'm on it". Writes events, commands, incidents,
  notifications, agent_log, pillow_state.night_state. Demo: `uv run sim/night_watch_demo.py`.

Not built yet, in rough order:
1. Base-laptop voice client: watch `pillow_state.night_state` for `check_in`, run `voice/checkin.py`,
   POST the result to `/checkin`. `Say` lines ("The light's on") have no route to that laptop yet.
2. Guardian (AGENT_FLOW 5): `agent_log.guardian` is always empty until it exists.
3. A sender for queued `notifications` (Twilio SMS / call, push). Nothing is actually sent today.
4. Personal night baseline from the `night_trips` view (timeout is a fixed 20 min).
5. Morning Brief (Factory Droid) and the Fetch.ai family agent.

Findings worth keeping:
- Daytime demo (judging 10:30): set the resident's `quiet_start` = `quiet_end` to watch all day.
- Cartesia's own volume control barely changes loudness (speech already peaks near full scale), so the
  check-in steps volume locally. Ink-2 has no language setting: it auto-detects, and once heard a
  mumble as French (handled as unclear). Its "Patient" turn settings suit slow, sleepy replies.
- On Windows, `import anthropic` takes 4-12 s; warm it up at startup, not on the first request.
  Opus 5.5 at low effort then answers in 1.3-3 s.
- Live tests all use `test-pillow` and clean up every row for it, so two people running the suite at
  once can race (seen once in `test_queue_and_poll`).
- Night Watch keeps timers in memory; after a restart it resumes from `night_state` (a check-in or
  alert in flight restarts as an immediate new check-in).

## Open team decisions (agents)

Defaults in brackets are what's built; settle together, then log the answer below.
1. Asks before the warning [3], warning cancel window [15 s], silence counted as no answer [8 s].
2. Mumbling (spoke, never understood): escalate like silence [yes], or faster?
3. Pillow voice: default [Gemma, en-GB placeholder] and how the owner picks (`residents.voice_id`).
4. Judge model: Opus 5.5 low effort [yes], or a faster Sonnet / Haiku (less careful on a safety call).
5. How many "I'm fine, still up" rounds before family hear anything [after the 2nd "fine", an info
   SMS, not an alarm]: never / after 1st / after 2nd / real escalation after N.
6. Check-in timeout: fixed 20 min [yes] or the personal baseline for the demo.
7. Guardian rules for the demo [proposed: brightness <= 40 % at night, max alerts per contact per
   night, block medical words, e.g. "she might have had a stroke"].

## Decisions log

- Fri 23 Oct: pillow, agentic (body = sensors/actuators). Persona leaning elderly-at-night;
  team to confirm.
- Fri 23 Oct: team bus = ntfy push via `coord/bus.py`; code in GitHub.
- Fri 23 Oct: lanes. Keanu electronics + firmware lead; Szymon backend, then pairs on wiring Sat
  morning; Adam product plus the non-electronic physical build (pod, base, cables); Adyan stays on
  agents (critical path).
- Fri 23 Oct: persona confirmed: adults 65+ living alone, not bedridden, who get up in the night.
- Fri 23 Oct: app owner = the person who sets the pillow up (usually an adult child). The resident
  has no app or login. Keep two roles in the data: `owner` (configures: quiet hours, timeout,
  contact order) and ordered `contacts` (who gets alerted; may include the owner, siblings,
  neighbours). Resident consents at setup and can pause by voice. Guardian caps sit above owner
  settings.
- Fri 23 Oct: personal night baseline (plain stats, not an LLM). Week one is "learning mode": fixed
  20 min no-return timeout + voice check-in from night one, trips only recorded. From week two,
  `checkin_timeout_min` = her usual trip length (≈p90 of past trips) + margin, clamped to 10–30 min;
  trips at unusual hours also flag. Drift (e.g. more trips per night over weeks) goes to family in
  the Morning Brief, never silently absorbed. Demo uses a hardcoded week of history.
- Sat 24 Oct: Adyan moves to hardware with Keanu; Adam takes over all agents, built in Szymon's
  backend (`szymon/app-scaffold`).
- Sat 24 Oct: agent flow and sponsor targets in `coord/AGENT_FLOW.md`. Core: Anthropic, Cartesia,
  Microsoft. Bets: Factory Droid (Morning Brief), Fetch.ai (family agent in ASI:One).
  Dropped: Atlassian (Forge/Jira only), Moss, ElevenLabs, Backboard.
- Sat 24 Oct: backend = Supabase (Postgres + Realtime) behind FastAPI, not Spacetime (Szymon + Adam
  agreed). Agents in Python against Supabase; family app via supabase-js Realtime. Trade-off
  accepted: no backend sponsor prize (Spacetime, Convex).
- Sat 24 Oct: ONE pillow only (Szymon). No kid pillow: the adult child / carer uses only the family
  app. Kid-pillow features move into the app: "Mum is in bed" glow becomes the live status card,
  `vibrate` / "Check on Mum" becomes the first ladder rung (in-app alert or push), the `keys.fine` ack
  becomes an "I'm on it" button that acknowledges the incident, and "who is awake" routing becomes
  on-call + quiet hours per contact. `pillow_id` `kid` and the `glow_presence` command are dropped.
- Sat 24 Oct: alert ladder never skips a contact (Adam + Szymon). Reachable contacts (on call,
  outside their own quiet hours) are tried first in priority order, the rest after them, so at 3am
  someone is always alerted. In-app alert goes to every contact at once first; "I'm on it" in the
  app = `POST /api/pillows/{id}/ack`. Built in Night Watch (PR #21).
