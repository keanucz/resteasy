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
judgement. Two pillows (parent ↔ adult child) share live state.

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
  stand in for DHT11; booth ESP32 + Waveshare still make two pillows.
- Only sensors go in the pillow; compute and power stay in a nightstand base. No LiPo or heater
  inside bedding. 3D printers (4, queued) for a vented sensor pod.
- Keypad: key 1 hold-to-talk, key 2 "I'm fine" (cancels escalation), key 3 call family.
- Lane split for hardware resolved Fri 23 Oct: see the decisions log.

## Decisions log

- Fri 23 Oct: pillow, agentic (body = sensors/actuators). Persona leaning elderly-at-night;
  team to confirm.
- Fri 23 Oct: team bus = ntfy push via `coord/bus.py`; code in GitHub.
- Fri 23 Oct: lanes. Keanu electronics + firmware lead; Szymon backend, then pairs on wiring Sat
  morning; Adam product plus the non-electronic physical build (pod, base, cables); Adyan stays on
  agents (critical path).
