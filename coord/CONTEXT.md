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
   that restlessness drops). 6. Routine: recurring reminders (meds, call family, walk the dog),
   buzzer then voice, never advises dosing. Built, see the decisions log (Sat 24 Oct, reminders).
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

- Ours: Keanu's Waveshare ESP32-S3 AMOLED 1.8" (mic, speaker, IMU, battery, Wi-Fi; enclosed, no
  header to wire), the Elegoo kit's bare ESP32-S3-N16R8, a 3-key
  keypad with a knob, ELEGOO Super Starter Kit (UNO R3 Project: DHT11, HC-SR04, photoresistors, LEDs,
  transistors, diodes, fan motor, buttons, IR remote; no PIR, IMU or mic), Szymon's Raspberry Pi +
  HTN badge. Full list: `firmware/PARTS.md`.
- Reserved from the booth (actual, Adam + Keanu + Szymon, awaiting pickup): 1 ESP32, 2 MPU6050,
  2 DC motors (vibration via off-centre weight, PN2222 + 1N4007 driver), 2 hit sensors (one each
  from Adam and Keanu), 2 microphone
  sound sensor modules, 2 temperature sensor modules (KY-001), 1 small passive buzzer module.
  Pickup window is 20 min after the Slack DM.
- Not reserved after all: touch sensors, heartbeat module, PIR, USB charger blocks, second ESP32.
  Implications: Night Watch needs a non-PIR trigger (MPU6050 head-off-pillow, sound sensor, or the
  HC-SR04 ultrasonic; the ELEGOO kit has no PIR); hit sensors can be "tap = I'm fine" alongside key 2 (one per pillow); KY-001 can
  stand in for DHT11. Only one pillow is built (see decisions log).
- In the pillow: the N16R8 "pillow node" with the sensors on its breadboard (foil head switch plate
  on GPIO4; the Uno is out), sending one contract line per 500 ms over ESP-NOW. Next to the bed:
  the Waveshare voice unit (mic, speaker, screen) on the laptop's USB. Power dangles outside the
  pillow: a USB power bank on one cable into the N16R8 (see decisions log, PR #36).
  No LiPo or heater inside bedding. 3D printers (4, queued) for a vented sensor pod.
- Keypad: key 1 hold-to-talk, key 2 "I'm fine" (cancels escalation), key 3 call family.
- Lane split for hardware resolved Fri 23 Oct: see the decisions log.

## Agents lane: status (Sat 24 Oct 13:15 PT, Adam)

Merged on master and deployed to Keanu's VPS (pillow.keanuc.net, PR -> master auto-deploys):
- `voice/` (PR #20): Cartesia Sonic 3.6 speaks, Ink-2 listens with turn detection; Claude Opus 5.5 (low
  effort, structured output) judges each reply as fine / confused / distress / unclear, keyword judge
  if the API fails. 3 asks, louder each time, then a warning with 15 s to say "I'm fine".
- `backend/app/agents/night_watch.py` (PR #21): Night Watch runs inside POST /state. POST /checkin takes
  the voice laptop's result, POST /ack is the app's "I'm on it". Demo: `uv run sim/night_watch_demo.py`.
- Guardian, Family Liaison, sleep events, family API, laptop voice client (`voice/checkin_client.py`),
  Morning Brief droid, Fetch family agent: Adyan's PR #30, detail in his section below.
- Reminders, the Routine agent (PR #37): see the decisions log (Sat 24 Oct, reminders). Live on the VPS.
- Personal night baseline (`backend/app/agents/baseline.py`, PR pending): see the decisions log
  (Sat 24 Oct, baseline). On `mum`'s seeded demo week: wait 14 min, usual trip 9 min, 2 long trips
  in the Brief. GET /night carries it as `summary.baseline`.

Not built or not yet run, in rough order:
1. A sender for queued `notifications` (Twilio SMS / call, push). The ladder writes rows but nothing
   reaches a phone yet: the demo's last hop.
2. A full dry run on the real hardware (pillow node -> Night Watch -> check-in through the Waveshare
   with live Cartesia -> Liaison -> phone). Each hop is tested alone; the whole chain never has been.
3. Morning Brief (Factory) and family agent (Fetch.ai) written but never run live: need
   `FACTORY_API_KEY` + Droid CLI, and `AGENT_SEED` + an Agentverse mailbox. No agent-to-agent hop yet
   (the family agent only calls the backend).

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

## Agents lane: status (Sat 24 Oct, Adyan, branch `adyan/guardian`)

Built on top of Adam's Night Watch and voice check-in, all tested without Supabase (live tests skip):
- `backend/app/agents/guardian.py`: every command / spoken line / alert passes it; verdict in
  `agent_log.guardian`. Caps brightness at 40 % at night, pulse 4-14 bpm, contract arg ranges, blocks
  medical claims (her own quoted words are allowed), max 6 alerts per contact per night, no repeat
  on one channel inside the step wait, SMS only with `contacts.sms_consent`, config whitelist.
- `backend/app/agents/sleep_events.py`: `restless`, `settled`, `asleep`, `key_talk`, `key_family`.
- `backend/app/agents/liaison.py`: Family Liaison, Claude Opus 5.5 with strict tools words each
  alert for its channel and one line for her; ladder stays plain code; fixed text on any failure.
- Family API (`backend/app/routers/family.py`): `GET /night`, `GET`/`POST /brief`, `PATCH /settings`,
  `POST`/`GET /goodnight`, `POST /goodnight/played`. Writes use the shared `CHECKIN_TOKEN`.
- `voice/checkin_client.py`: base laptop watches `night_state`, speaks the path-light line, runs the
  check-in and posts the result, plays queued goodnight messages.
- `droid/morning_brief.py`: Factory Droid at 06:00, read-only workspace, structured note + diff.
- `agents/fetch/family_agent.py`: uAgent on Agentverse (chat protocol) for ASI:One.

Needs: `ANTHROPIC_API_KEY` in `backend/.env` (Liaison), re-run `supabase/seed.sql` (sets
`sms_consent = true` for Sarah and Test User, or the Guardian blocks their SMS), Droid CLI +
`FACTORY_API_KEY` on the laptop that runs the brief, `AGENT_SEED` for the family agent.

## Open team decisions (agents)

Defaults in brackets are what's built. 1-4, 6 and 7 settled by Adam on Sat 24 Oct (decisions log);
still open:
5. How many "I'm fine, still up" rounds before family hear anything [after the 2nd "fine", an info
   SMS, not an alarm]: never / after 1st / after 2nd / real escalation after N.

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
- Sat 24 Oct: no base / pedestal box (Keanu). The booth ESP32, its power and USB sit on the
  nightstand, still outside the pillow; nothing else changes. Parts list in `firmware/PARTS.md`.
- Sat 24 Oct: pillow senses, a bedside unit talks (Keanu, PR #36). The Waveshare is enclosed, so
  the Uno can't be wired to it. The Uno + the bare N16R8 go in the pillow; the N16R8 sends every Uno
  line over ESP-NOW (no access point, nothing beacons) to the Waveshare at the bedside, on the
  laptop's USB. It prints them as `UNO {...}` and the talk key as `KEY talk`, so
  `sim/audio_bridge.py --serial <Waveshare port>` is unchanged. Power dangles outside the pillow
  on one cable: the starter kit's 9 V battery in the Uno's barrel jack, a USB power bank as backup.
  No CONTRACT, backend or agent change. Adam's `buzz` command plays on the voice unit's speaker
  (no buzzer in this layout). **Update (Keanu, same day): the Uno is dropped.** The sensors go
  straight onto the N16R8's breadboard and it builds the same JSON line itself (Adyan, in progress).
- Sat 24 Oct: reminders = the Routine agent (Adam; from talking to two older women outside the
  venue: what they forget is recurring commitments). Adam builds backend + voice; Szymon builds the
  app page, Keanu the buzzer. **Schema (live, migration `20261024185028_reminders`):** `reminders`
  (per resident: `label` as an action phrase, `kind` meds/call/custom, `time_of_day` in her
  timezone, `days` ISO 1=Mon..7=Sun, `confirm`, `active`) and `reminder_occurrences` (one per due
  time, unique `(reminder_id, due_at)`; `status` waiting/due/announced/done/missed, `attempts`,
  `reply` as a transcript, never audio). Both are app-readable and in Realtime. `commands.cmd` gains
  `buzz` (CONTRACT.md §3). Rules (plain code, `backend/app/agents/reminders.py`): a due reminder
  waits until `night_state` is `awake` (never wakes her, never talks over a check-in). Per
  reminder, `confirm` off = buzz + say once; on = buzz, say, listen, Claude judges (keyword
  fallback); "not yet" or silence → one retry 10 min later, then missed; anything open 3 h after its
  time → missed. Distress in a reply escalates through Night Watch (incident kind `distress`).
  Laptop side in `voice/checkin_client.py` + `voice/reminder.py`. API: `GET|POST
  /api/pillows/{id}/reminders`, `PATCH|DELETE .../reminders/{rid}`, `GET .../reminders/today`,
  `GET .../reminders/due`, `POST .../reminders/{occurrence_id}/result` (bearer `CHECKIN_TOKEN`).
- Sat 24 Oct: repo migrations now match live Supabase. `link_contacts_to_auth_users` (adds
  `contacts.user_id` → `auth.users`) and `drop_glow_presence` had been applied live without being
  committed; both are added to `backend/supabase/migrations/` under their live versions.
- Sat 24 Oct: the Uno is out (Keanu + Adyan). The foil head plate goes straight onto the N16R8
  pillow node (GPIO4, `INPUT_PULLUP`), which builds the same contract line the Uno printed, so
  `sim/uno_state.py`, the bridge and the backend are unchanged. One USB cable from a power bank
  outside the pillow powers the node. `firmware/pillow_uno/` kept for reference.
- Sat 24 Oct: agent open decisions settled (Adam). (1) Check-in timing stays as built: 3 asks, each
  louder, 8 s silence = no answer, then a warning with 15 s to say "I'm fine". (2) Mumbling (spoke,
  never understood) escalates like silence. (3) Pillow voice: en-US placeholder, Cartesia "Skylar"
  (`db6b0ed5-d5d3-463d-ae85-518a07d3c2b4`, Jacqueline as fallback) since we demo in SF; spoken lines in
  American English. Voice choice in the family app is a TODO (`residents.voice_id` exists, unread).
  (4) Judge = Opus 5.5 at low effort. (6) Build the personal night baseline from the past week of
  `night_trips` (rules as in the Fri 23 Oct baseline entry); next feature in the agents lane.
  (7) Guardian rules as built: brightness <= 40 % at night, max 6 alerts per contact per night,
  medical words blocked. (5) still open.
- Sat 24 Oct: personal night baseline rules (Adam; plain code, `backend/app/agents/baseline.py`).
  Window = the 7 nights before the current night (night = 18:00 to noon). Usual trip = under 20 min;
  longer trips never move the baseline, they go to the Brief as "not counted as usual". Learning
  mode until >= 5 usual trips on >= 4 nights. Learned wait = p90 of usual trips (nearest rank) + 5
  min, clamped to the Guardian's 10-30. **Owner vs learned: the shorter wins**
  (`min(owner checkin_timeout_min, learned)`): the owner's value (app #45, PATCH /settings, brief
  diff) is the longest she's ever left, learning only brings a check-in sooner, and a demo value
  below 10 set by SQL still wins. Night Watch re-reads it with the other settings (every 60 s) and
  logs a change to agent_log (tool `baseline`). Unusual hour = a trip starting > 60 min outside the
  week's earliest-latest start. Drift lines in `summary.unusual`: last night's trips >= the week's
  average + 1 (and >= 2), each long trip, and learned > owner ("she may be checked on during
  ordinary trips"). No schema change; one week of data, so no multi-week trend yet.
