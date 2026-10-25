# Product

<!-- impeccable:product-schema 1 -->

## Platform

ios

The app is one Expo (React Native) codebase that ships the same custom identity on iOS and Android; it does not switch design language per OS. `ios` is recorded so touch targets, safe areas, haptics and navigation follow iOS expectations; Android must work, not look different.

## Users

- **Owner (primary):** the adult child who sets the pillow up for a parent. They configure quiet hours, the check-in timeout and the contact order, and they are usually the first person alerted. They open the app at night, often half asleep, sometimes in a stressful moment (an alert), and in the day to look back at how the night went.
- **Contacts:** an ordered list of people who get alerted (may include the owner, siblings, neighbours).
- **Resident:** an adult aged 65 or over who lives alone, is not bedridden and gets up in the night. The resident has **no app and no login**. They consent at setup, interact only with the pillow (voice, keypad: hold to talk, "I'm fine", call family) and can pause it by voice.

## Product Purpose

An agentic pillow that watches over an older parent at night: sensors in the pillow, actuators (voice, vibration) at the bedside, Claude deciding. When she gets up and does not come back, it checks in by voice, then escalates to family, least intrusive first. The app is the family's window onto the night: live status, the night so far, alerts with an "I'm on it" acknowledgement, history and settings.

Success: the adult child sleeps better because they trust the pillow to tell them only when it matters, and the parent keeps living independently without wearing a device.

## Positioning

Pitch line: "Not a monitor. A goodnight."

- Nobody owns the night with an agent. Lumi, Bloom and The Village AI are daytime companions; Somnox is a fixed-program breathing cushion; medical alert pendants are rarely worn (only 9% of people 65+ use one, 18% of those wear it all the time).
- The pillow needs nothing worn and no screen for the resident: it feels her get up.
- Escalation is least intrusive first and never auto-calls emergency services.

## Operating Context

- Night use is the main scene: a phone picked up in a dark bedroom at 2 am, read in seconds.
- Alerts arrive as push notifications and in the app; the owner acknowledges ("I'm on it") so the escalation chain stops or moves on.
- Week one is "learning mode" (fixed 20 minute no-return timeout); from week two the timeout follows her usual trip length. Drift (more trips per night over weeks) is reported to family in the night summary, never silently absorbed.
- Hackathon context: Cal Hacks 13.0, a 2 minute live demo with a hardcoded week of history. Judging weighs intentionality: every design choice needs a clear who and why.

## Capabilities and Constraints

- Stack: Expo SDK 58, React Native 0.88, Expo Router, NativeWind 4 + Tailwind 3.4, Reanimated 4, react-native-svg (in `frontend/`). Backend: Supabase (Postgres, Realtime, Auth) behind FastAPI; agents in Python.
- Auth: email + password (Supabase Auth). Older demo logins made as a plain name log in as `<name>@pillow.test`.
- Live states for the resident: asleep, restless, up, alert (hasn't come back), offline.
- The app sends and receives pillow signals only through the backend contract, never directly.
- Timers and thresholds are plain code (a state machine); the LLM does language and judgement.
- Guardian rules sit above owner settings: quiet-hour caps, a maximum number of alerts, no medical claims, no raw audio.
- Terminology: "pillow", "owner", "contacts", "check-in", "learning mode", "night summary", "I'm on it".

## Brand Commitments

- **Name:** "Rest Easy" (the app). "Pillow" stays the word for the device.
- **Mascot:** a sleepy hedgehog tucked in under a blanket ("Tucked in"), the logo.
- **Tagline:** placeholder "Sleep tight. We'll keep watch." until the team settles one. The pitch line "Not a monitor. A goodnight." is the team's.
- **Voice:** undecided. To be decided together with the Cartesia voice work once that is merged into master.
- **Status in words:** the resident's state is said in plain words ("Mum is asleep"), never as a pill, badge or chip.

## Evidence on Hand

- About a quarter of falls in older adults happen overnight; two or more night bathroom trips more than double fall and fracture risk (NIH StatPearls, Nocturia).
- Only 9% of people 65+ use a medical alert device and only 18% of users wear it all the time (The Senior List 2026).
- Demo data: a hardcoded week of night history.
- No real customers, testimonials, clinical validation or pricing exist. Never invent them, and never make medical claims.

## Product Principles

1. Least intrusive first: app alert, then text, then call, then the next person. Never auto-call emergency services.
2. Say only what matters: the owner should trust that silence means a quiet night.
3. Respect the resident: consent at setup, pause by voice, no raw audio, no medical claims.
4. Readable at 2 am: the state is clear in a glance from a phone picked up in the dark.
5. The pillow does the work; the resident never needs a screen.

## Accessibility & Inclusion

- Night use by tired owners: high contrast and large, plain wording; dark mode is the default.
- Honour reduced motion and dynamic type; touch targets at least 44 by 44 points.
- Alerts must be understandable without colour alone (the state is always written out).
