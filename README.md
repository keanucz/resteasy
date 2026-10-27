<p align="center">
  <img src="frontend/assets/logo/pillow-hedgehog.svg" alt="Rest Easy: a sleepy hedgehog tucked in under a blanket" width="240">
</p>

<h1 align="center">Rest Easy</h1>

<p align="center"><b>Not a monitor. A goodnight.</b><br>
A pillow that notices when an older parent gets up in the night and doesn't come back, asks if
they're okay, and tells the family if they aren't.</p>

<p align="center">Built in one weekend at <b>Cal Hacks 13.0</b> in San Francisco, October 2026.</p>

<p align="center">
  <img src="docs/images/app-asleep-dark.png" alt="The app at night: Mum is asleep, in bed since 10:42 pm" width="200">
  <img src="docs/images/app-up-light.png" alt="The app in light mode: Mum is up, out of bed since 2:14 am" width="200">
  <img src="docs/images/app-alert-dark.png" alt="The app on an alert: Mum hasn't come back, up for 9 minutes and she didn't answer the pillow" width="200">
</p>

---

## Why we built it

About a quarter of falls in older adults happen at night, and people who get up to use the
bathroom two or more times a night have more than double the risk of a fall or fracture (NIH
StatPearls, *Nocturia*). The usual fix is a medical alert pendant. Only 9% of people over 65 use
one, and only 18% of those wear it all the time (The Senior List, 2026). A pendant on the bedside
table doesn't help anyone.

So we started from the thing everyone already uses every night. Rest Easy is for an older adult
who lives alone, isn't bedridden and gets up in the night, and for the son or daughter who lies
awake wondering whether she's alright. She doesn't wear anything or look at a screen. The pillow
knows when her head is on it. If she gets up and is gone for longer than her usual trip, the pillow
asks her, in a voice she knows, whether she's okay. If she doesn't answer, or says she needs help,
it tells her family, starting with the gentlest option. It never calls emergency services by
itself.

## What it does

**It feels when she's in bed.** Inside the pillowcase there's a plate made of two sheets of
kitchen foil on cardboard. When her head presses down, the sheets touch and pull a pin on the
ESP32-S3 low. That's all the sensing there is: no camera, nothing to wear, and no audio is ever
stored.

<p align="center">
  <img src="docs/images/build-foil-plate-open.jpg" alt="The foil head plate opened up on the table next to the ESP32 breadboards" width="420">
  <img src="docs/images/build-foil-plate-pressed.jpg" alt="A hand pressing the closed plate, as a head would" width="420">
</p>

**It checks in by voice.** Once she's been up longer than her usual trip, the bedside speaker asks
whether she's okay. It tries up to three times, a little louder each time. Claude reads each reply
and sorts it into *fine*, *confused*, *distress* or *unclear*.

**It tells the family, gently first.** Silence or a call for help starts a ladder: an alert in the
app, then a text, then a phone call, then the next person on the list. Tapping "I'm on it" in the
app stops it. If she sounds distressed, everyone gets a call straight away.

<p align="center">
  <img src="docs/images/alert-texts-first.png" alt="Text messages on a family member's phone: two alerts saying Margaret got up at 00:21 and at 00:35, hasn't come back to bed, and the pillow's check-in didn't finish, so please check on her" width="280">
  <img src="docs/images/alert-texts-later.png" alt="More alert texts: Hello Szymon, this is a message about Margaret. She got out of bed at 00:35 and it has been 18 minutes. Then Margaret is back in bed, and a new alert for 01:10" width="280">
</p>

These are the texts that reached a family member's phone during our test runs early on Sunday
morning. Each one says when she got up, how long she's been gone and whether the check-in
finished. When she gets back into bed, a short "Margaret is back in bed" follows. We cropped the
sender's number off the top.

**It learns her normal.** For the first week it waits a fixed 20 minutes. After that, the timeout
follows how long her trips usually take, and the family's night summary points out any trip that
ran much longer than usual.

**It helps her get back to sleep.** If she says "I can't sleep", the pillow plays ten minutes of
quiet music or rain. A key press, a check-in or getting up stops it. It also reads out reminders
like "take your tablets" or "call your daughter", but it never gives advice about doses.

**It speaks in a family voice.** Someone in the family records a short sample in the app.
Cartesia clones it, so the check-ins and the alert phone calls sound like her own family rather
than a stranger.

<p align="center">
  <img src="docs/images/app-family-voice.webp" alt="Screen recording of Add a family voice: a short passage to read aloud, a timer counting up while recording, then Recording ready, 14 seconds" width="260">
</p>

Recording a family voice in the app. It shows a short passage to read aloud and counts the
seconds; this take stopped at 14.

**Family can ask an agent about her night.** Each family member gets a Fetch.ai agent on
Agentverse. In ASI:One they can ask "How was Mum's night?" or tell it "I'm away Thursday to
Sunday, make sure Mum's covered."

The resident herself never needs an app or a login. She agrees to it at setup, and after that she
either talks to the pillow or uses a small three-key pad by the bed with *talk*, *I'm fine* and
*call family*.

## The app

The family app is built with Expo and runs on iOS and Android. Its main screen says what's
happening in plain words ("Mum is asleep", "Mum hasn't come back") and doesn't rely on colour
alone, because it's meant to be read half awake at 2 am. Below that is a ribbon showing the night
so far and a short summary of last night. It opens in dark mode by default, and light mode is a
setting.

<p align="center">
  <img src="docs/images/app-login.png" alt="Rest Easy login screen: Sleep tight. We'll keep watch." width="200">
</p>

The screenshots on this page come from the app running in a browser with sample data for one
night, so the times in them are made up.

The three clips below are screen recordings from an iPhone running the app on Sunday morning,
sped up and trimmed. The resident in them is called Margaret.

<p align="center">
  <img src="docs/images/app-tonight-live.webp" alt="Screen recording of the Tonight screen changing from Margaret is up to asleep, restless, asleep and up again, ending with: The pillow is checking in" width="240">
  <img src="docs/images/app-night-summary.webp" alt="Screen recording scrolling through the night: Family were alerted, time asleep and out of bed, bedroom temperature, movement, a log of what the pillow noticed, and four weeks of sleep" width="240">
  <img src="docs/images/app-add-reminder.webp" alt="Screen recording of adding a reminder to have a glass of water at 11 am every day, showing the question the pillow will ask Margaret first, then Reminder saved" width="240">
</p>

On the left, the Tonight screen changes as her state does: up, asleep, restless, asleep, then up
again with "The pillow is checking in" under her name. In the middle is the rest of that
screen, from the alert card down through temperature, movement and the log of everything the
pillow noticed overnight. On the right, a family member adds a water reminder. Before it starts,
the pillow asks Margaret whether that's alright.

## How it works

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/diagrams/system-flow-dark.png">
  <img src="docs/images/diagrams/system-flow-light.png" alt="How Rest Easy fits together: the foil head plate and pillow node in the bedroom, the voice unit and laptop at the bedside, the backend's Night Watch, Family Liaison, Guardian and Notify, and the family app" width="100%">
</picture>

<details>
<summary>Mermaid source for the system diagram</summary>

```mermaid
flowchart LR
  subgraph Bedroom
    plate["Foil head plate"] --> node["ESP32-S3 pillow node<br/>(in the pillow)"]
    node -- "ESP-NOW" --> unit["Waveshare ESP32-S3 voice unit<br/>(mic + speaker, bedside)"]
    pad["3-key pad<br/>talk / I'm fine / call family"]
  end

  subgraph Laptop["Bedside laptop"]
    bridge["audio_bridge.py"]
    client["checkin_client.py<br/>voice check-in"]
  end

  unit -- "USB serial: state + audio" --> bridge
  pad --> client
  bridge <-- "pillow audio" --> client

  subgraph Cloud["Backend (FastAPI + Supabase)"]
    nw["Night Watch<br/>state machine"]
    liaison["Family Liaison<br/>(Claude)"]
    guardian["Guardian<br/>rules check"]
    notify["Notify<br/>push / SMS / call"]
    db[("Supabase<br/>Postgres + Realtime")]
  end

  bridge -- "POST /state" --> nw
  client <-- "night_state, POST /checkin" --> nw
  nw --> liaison --> guardian --> notify
  nw <--> db

  client <-- "TTS + STT" --> cartesia["Cartesia<br/>Sonic 3.6 / Ink-2"]
  client -- "judge reply" --> claude["Claude Opus 5.5"]
  notify -- "SMS, voice call" --> phone["Family phones"]
  notify -- "Line voice agent" --> cartesia
  db -- "live status" --> app["Rest Easy app<br/>(Expo, iOS + Android)"]
  app -- "I'm on it, settings" --> nw
  fetch["Fetch.ai agents<br/>(Agentverse / ASI:One)"] <--> nw
```

</details>

The pillow node sends its state over ESP-NOW to the voice unit by the bed, which passes it to a
laptop over USB. The laptop forwards state changes to the backend and runs the voice check-in.

We kept the decisions out of the language model on purpose. The timers, thresholds and the
escalation ladder are ordinary code in a state machine (`backend/app/agents/night_watch.py`), so
the same night always produces the same alerts. Claude is used for two jobs: working out what she
said, and writing each alert so it reads well as a push notification, a text or a phone call.
Everything the system is about to say or send goes through a rules check we call the Guardian
first. It limits alerts during quiet hours, caps how many alerts one person can get in a night,
and blocks medical claims and raw audio.

### Night Watch

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/diagrams/night-watch-dark.png">
  <img src="docs/images/diagrams/night-watch-light.png" alt="Night Watch states: Awake, In bed, Up, Check-in and Escalating, and what moves her between them" width="100%">
</picture>

<details>
<summary>Mermaid source for the state diagram</summary>

```mermaid
stateDiagram-v2
  [*] --> Awake
  Awake --> InBed: head on the plate
  InBed --> Up: head off for 10 s
  Up --> InBed: back in bed
  Up --> Awake: up for the day (morning)
  Up --> CheckIn: up longer than her usual trip
  CheckIn --> Up: "I'm fine"
  CheckIn --> Escalating: no answer, distress, or a call for help
  CheckIn --> InBed: back in bed
  Escalating --> InBed: back in bed
  Escalating --> Up: she says "I'm fine"
```

</details>

When she says she's fine, the pillow believes her but asks again a bit later. If she says "I'm
fine" twice during the same trip, the family get a heads-up for information, not an alarm.

### A check-in that needs family

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/diagrams/checkin-sequence-dark.png">
  <img src="docs/images/diagrams/checkin-sequence-light.png" alt="A check-in that needs family, step by step, from the pillow to Night Watch, the voice check-in, Claude, the Family Liaison and Guardian, and the family" width="100%">
</picture>

<details>
<summary>Mermaid source for the sequence diagram</summary>

```mermaid
sequenceDiagram
  autonumber
  participant P as Pillow
  participant NW as Night Watch
  participant V as Voice check-in
  participant C as Claude
  participant L as Family Liaison + Guardian
  participant F as Family

  P->>NW: head off the plate
  Note over NW: she's been up longer<br/>than her usual trip
  NW->>V: start check-in
  loop up to 3 asks, louder each time
    V->>P: "Are you okay?" (in the family's voice)
    P-->>V: her reply, or silence
    V->>C: fine / confused / distress / unclear?
  end
  V->>NW: no answer
  NW->>L: escalate
  L->>F: app alert
  L->>F: text, then a phone call
  L->>F: next contact, if no one answers
  F-->>NW: "I'm on it"
  NW-->>L: stop the ladder
```

</details>

## Building it

<p align="center">
  <img src="docs/images/team-testing-pillow.jpg" alt="The team at their table in the hall, one hand on the pillow during a test" width="420">
  <img src="docs/images/team-at-the-table.jpg" alt="Three of the team at the table giving a thumbs up" width="420">
</p>

There were four of us, and each person worked with their own Claude Code session. The four
sessions talked to each other over a small message bus we wrote for the weekend, so one person's
Claude could ask another's about an API change without either of us relaying it by hand.
`coord/` has the protocol and a few screenshots of it in use.

<p align="center">
  <a href="docs/images/build-overnight-timelapse.mp4"><img src="docs/images/build-overnight-timelapse.webp" alt="Sped-up timelapse of the team working at our table early on Sunday morning, with the pillow on the table between the laptops" width="640"></a>
</p>

A timelapse from our table, starting around 4:30 am on Sunday. The pillow sits between the
laptops. Click it for a sharper mp4 version.

## Repository

| Path | What's there |
|---|---|
| `backend/` | The FastAPI service: Night Watch, the Guardian, the Family Liaison, reminders, night summaries and baselines, notifications (Twilio and Cartesia Line), and the Supabase migrations and seed data. |
| `frontend/` | The Rest Easy family app (Expo SDK 58, React Native, Expo Router, NativeWind). |
| `voice/` | Everything the bedside speaker does: the check-in client, Cartesia speech in and out, the Claude reply judge, settle music, reminders and the keypad. |
| `firmware/` | Arduino sketches for the ESP32-S3 pillow node and the Waveshare voice unit, plus diagnostics. The parts list is in `firmware/PARTS.md`. |
| `sim/` | The laptop audio bridge, serial bridges, and simulators that run a whole night without any hardware. |
| `agents/fetch/` | The Fetch.ai coordinator and family agents (uAgents, Agent Chat Protocol). |
| `deploy/` | Docker Compose, the Cloudflare tunnel config and the deploy script. Merging to `master` deploys. |
| `coord/` | The message bus and protocol the four Claude Code sessions used. |
| `docs/images/` | The screenshots and photos in this README. |
| `PRODUCT.md`, `DESIGN.md` | Who it's for, the product principles, and the design system. |

## Running it

The backend needs Python 3.12, [uv](https://docs.astral.sh/uv/), a Supabase project, and its keys
in `backend/.env` (`backend/README.md` lists them):

```bash
cd backend
uv run uvicorn app.main:app --reload --port 8000
uv run pytest   # Supabase tests skip without SUPABASE_URL / SUPABASE_SECRET_KEY
```

To play through a whole night without the hardware:

```bash
uv run sim/night_watch_demo.py
```

To run the app:

```bash
cd frontend && npm install && npx expo start
```

Setting up the bedside voice and the pillow bridge is covered in `voice/` and `firmware/README.md`.

## Principles

1. **Least intrusive first.** An app alert comes before a text, a text before a call, and a call
   before the next person. It never calls emergency services by itself.
2. **Only say what matters.** If the family hear nothing, it should mean she had a quiet night.
3. **Respect the resident.** She consents at setup and can pause it by voice. No raw audio is
   kept, and it makes no medical claims.
4. **Readable at 2 am.** Her state is always written out in words ("Mum is asleep"), not shown by
   colour alone.
5. **The pillow does the work.** She never has to look at a screen.

Rest Easy is a hackathon prototype. It isn't a medical device, it hasn't been clinically tested,
and it shouldn't replace emergency services or professional care.

## Team

Built at Cal Hacks 13.0 by Keanu Czirjak (hardware and firmware), Adam Kassam (agents and voice),
Szymon Arciszewski (backend, notifications and the app) and Adyan Ullah (hardware + video).
