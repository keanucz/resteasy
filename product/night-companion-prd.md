# Return to sleep companion PRD

Status: Ready for implementation planning by the hive. Requested by Adyan, 24 October 2026. This document authorizes a proposed feature scope; it does not claim implementation, deployment, or reassignment of another teammate's lane.

> **State of master when this was filed (Adyan's Claude, Sat 24 Oct ~23:40 PT; verify before planning).**
> - `voice/talk.py` (PR #61, merged) already does the "Set a reminder" and "What have I got tomorrow" parts: hold the talk key, Claude turns her words into a structured `set_reminder` / `list_reminders` request, plain code reads it back, yes/no via `judge.py`, then `POST /reminders?as=resident` with the agent token; the backend records `consent=agreed` because she confirmed the read-back. Build the companion on this, don't duplicate it.
> - Reminder routes use `CareActorDep` / `ContactActorDep` (PR #58, #61, #69), not `CareLoginDep`. `?as=resident` is the resident-scoped capability this PRD asks for; the per-tool allowlist, confirmation expiry and idempotency key on top of it are still to build.
> - Not on master yet: `night_companion_enabled` flag, calendar adapter / labeled demo schedule, morning basket table and cards, bundled calming audio with timer/fade/stop, companion preferences, audio arbitration between companion playback and the safety check-in.
> - Mic/speaker path: `sim/audio_bridge.py` on Keanu's laptop (hotspot link, BLE fallback, USB fallback) is the only audio owner; the macro pad (`voice/keypad.py`) gives talk / fine / family keys with key-down and key-up.

## Product outcome

Help an older adult who wakes during the night put a worry down by listening, taking a small authorized practical action, and offering a quiet transition back to rest. The pillow should make it easier to disengage from technology. Conversation length is not a success metric.

Primary user: an older adult living independently who wakes at night and worries about tomorrow. Supporting user: a family member who helps configure the device and receives only information the resident has chosen to share.

Product promise: "Tell it what is on your mind. It can help you check tomorrow, remember something, or simply settle down."

Use the resident-facing name **Night companion**, with **Talk it through**, **Take care of tomorrow**, and **Help me settle** modes. Provide a warm, supportive conversational style. Do not present it as a therapist, diagnose a condition, deliver treatment, or promise that an action will make someone sleep.

## Existing system and integration constraints

Read `CLAUDE.md`, `coord/PROTOCOL.md`, `coord/CONTEXT.md`, `coord/CONTRACT.md`, and `coord/AGENT_FLOW.md` before implementing. Reconcile current code with these notes: some older descriptions of sensors, voice timing and deployment are stale.

Reuse the existing Claude and Cartesia voice path, Guardian, Night Watch, reminders, family app, and FastAPI/Supabase backend. Keep this feature behind `night_companion_enabled`, initially off. No new hardware or second voice provider is required.

Relevant existing seams:

- `voice/checkin_client.py`, `voice/talk.py`: voice orchestration and device integration.
- `voice/reminder.py`, `voice/judge.py`: existing reminder speech and classification.
- `backend/app/agents/`: Night Watch, Guardian, reminder scheduling, baseline and events.
- `backend/app/routers/reminders.py`: reminder writes take a care-circle login, a family agent's own token, or the agent token with `?as=resident`; device result reports use a different authorization path.
- `backend/app/routers/family.py`: family-facing flows.
- `frontend/src/`: family app; inspect current screens before choosing placement.

Do not expose a family login, database service key, or unrestricted reminder CRUD access to the language model. Backend ownership must establish a resident-scoped voice-action capability that checks device identity, enabled permissions, confirmation and Guardian approval. The existing reminder calendar represents reminder occurrences; it is not evidence of external appointments.

## MVP scope

| Capability | Required behavior |
|---|---|
| Talk it through | Brief acknowledgment, then ask whether the user wants listening or practical help. One question at a time. |
| Check tomorrow | Read a connected calendar through an adapter, or an explicitly labeled demo schedule. Read only the relevant event, with its actual date and time. |
| Set a reminder | Create a one-time reminder through the existing reminder service after the resident confirms the interpreted action and time. |
| Morning basket | Save a short, resident-approved task or concern for a chosen morning review. Saving is not completing the task. |
| Calming audio | Play one of a small set of bundled, licensed or original tracks with a timer, fade and stop control. No streaming account required. |
| Preferences | Explicitly remember a preferred audio choice, default duration and whether post-return offers are welcome. |
| Visible execution | Show action status and evidence of successful writes in the appropriate app view and technical log. |

Stretch only after MVP acceptance: live calendar OAuth if not already available, family-message drafts, short stories, optional guided relaxation, multilingual flow, and family-approved morning brief integration. Sending messages, booking rides, purchases, calendar edits, medical advice and autonomous browsing are outside MVP.

## Main user journey

1. Resident intentionally activates Talk and says "I can't sleep; I'm worried about tomorrow." The companion starts a session. Preserve the existing microphone activation contract. No always-listening wake word is introduced.
2. Pillow: "Would you like me to listen, or help with something for tomorrow?"
3. Resident: "I'm worried I'll forget my appointment." Pillow offers to check the authorized schedule.
4. Calendar result: "Your appointment is Sunday, October 25 at 10 a.m. Shall I remind you at 8 a.m. that morning?" Use the resident's timezone and an absolute date to resolve midnight ambiguity.
5. Resident confirms. Backend persists exactly one reminder and returns its identifier and status. Only then: "Your reminder is set." If existing reminder consent is pending, report pending instead and complete the existing consent flow; never report it active prematurely.
6. Resident: "I also need to arrange a ride." Pillow offers to save that task for morning. It does not imply a ride has been arranged.
7. After confirmation and successful persistence: "Arranging a ride is on your morning list. Would you like ten minutes of your usual music?"
8. Play requested audio, fade to silence, close the listening window. Physical Stop/Talk interruption remains available. The session ends without a follow-up prompt after the music ends.

A bed-return event may offer this experience only when the resident has opted in and a wakeful interaction has been detected. Bed return or movement alone must not start speech or imply wakefulness. Default to resident initiation. Offer at most once per return episode, and do not repeat after silence or decline.

## Conversation requirements

- Default replies: one or two short sentences, one question, no list of all capabilities unless asked.
- For grief, loneliness or an unresolvable concern, acknowledge without inventing a task. Example: "That sounds hard tonight. Would you like to tell me about it, or have some quiet company?" Do not promise permanent companionship or discourage human relationships.
- Do not infer permission from distress, silence, ambiguous speech or the model's confidence. Confirm durable writes with a concrete readback; "remind me at eight" requires clarification when AM/PM or date is uncertain.
- "Never mind", "stop" and the physical stop control cancel pending proposals and stop audio. A successfully saved reminder remains saved unless the user explicitly requests its cancellation; explain this if relevant.
- If there are no events in a successfully queried range, say so. If a calendar is unavailable, say it could not be checked. Never substitute "nothing scheduled" for failure.
- Do not announce sleep detection or claim therapeutic outcomes from reduced motion.
- Ordinary emotional worries stay in the companion flow. Explicit requests for urgent help or immediate danger interrupt it and enter the established assistance flow. Do not claim "help is coming" until a person has actually acknowledged; report the true contact status.

## Agent and execution design

Use a single companion orchestrator with bounded tools. Do not add multiple model agents merely to create more agents. Claude interprets language and proposes a response/action. Deterministic code owns identity, permissions, confirmation, timers, priorities, persistence, retries and cancellation.

Proposed session states: `idle → listening → responding → awaiting_confirmation → executing → settling → ended`. Read-only questions can go directly from responding to listening. Failures return a truthful explanation. Urgent assistance preempts all companion states.

Proposed internal tool contracts, to finalize with the backend lane before implementation:

| Tool | Inputs | Result and constraints |
|---|---|---|
| `read_schedule` | Authorized resident context, start/end instants | Events, source, fetched time, timezone, and availability status. Read-only. |
| `propose_reminder` | Label and intended local date/time | Validated proposal, exact readback, expiration; no write. |
| `confirm_action` | Proposal ID and confirmed session turn | Persist once; return `succeeded`, `pending`, `failed` or `unknown`, plus resource ID. |
| `propose_morning_item` | Short task text, review time, visibility | Proposal requiring resident confirmation; no transcript attached. |
| `play_audio` | Allowlisted track ID, duration, volume | Actual playback state; timed stop and fade. |
| `stop_audio` | Current session/playback ID | Stop immediately, clear queued playback. |
| `set_preference` | Allowlisted preference and value | Persist only after explicit request or confirmation. |

Every write uses an idempotency key bound to session and proposal. Retrying a timed-out request must retrieve or reconcile its result before creating another resource. A delayed result from a canceled proposal must not start a new action. If a committed action races with cancellation, surface its actual status and offer an explicit undo where supported.

Schedule text and task titles are untrusted content, never agent instructions. Tool outputs must not grant permissions. Use structured allowlisted arguments, not executable code or model-generated URLs.

## Audio arbitration and device behavior

Priority: explicit help / active safety check-in > resident Stop > companion conversation > calming playback. Routine reminders retain their existing wakefulness requirements and must not talk over any higher-priority flow.

Only one speech/listening/playback owner at a time. Stop or duck music before listening to prevent the speaker from transcribing itself. An active safety check-in cancels companion audio and pending proposals. Do not automatically resume them after the incident. Preserve existing brightness and volume caps; do not add breathing lights to the MVP.

Silence in an optional companion conversation ends it quietly. Silence in the existing safety check-in retains its existing escalation behavior. These are different states and must not share a generic silence handler.

Initial configurable demo defaults: ten minutes of audio, ten-second fade, existing patient listening settings, and a five-minute inactivity expiry for pending action proposals. These are product defaults to evaluate, not clinical recommendations.

## Family app and privacy

Add a small companion settings section and a Morning basket view rather than another dashboard. Show actionable cards with accurate states: saved for morning, reminder pending consent, reminder active, completed, failed, or canceled. Do not label a saved worry "resolved."

Default: no raw audio storage, no persistent full conversation transcript, and no family access to intimate conversational content. Persist only approved tasks/actions and opted-in preferences. Before saving a morning item, state who can see it. If resident-private items cannot be protected from family readers in the MVP, offer only an explicitly shared task and say so before confirmation.

Technical logs retain action IDs, timing, tool type, outcome and Guardian verdict; redact personal worry text. Calendar access is resident-specific and revocable. Family readers must be explicitly authorized for that resident; knowing a pillow ID is insufficient. New exposed data requires suitable row-level access controls. Backend lane owns schema, migrations and access tests.

## Failures and graceful behavior

| Failure | Expected behavior |
|---|---|
| Calendar disconnected or stale | Explain unavailable/stale status; ask for the appointment time or offer a morning task. |
| Reminder save fails | Say it was not saved; offer retry. Never say "I'll remember" without a durable result. |
| Save response times out | Reconcile by idempotency key; report uncertainty until resolved. |
| Model or network unavailable | Offer supported cached audio and physical stop; no invented conversational or write success. |
| Audio asset missing | Say playback is unavailable; return to quiet. |
| Device reconnect or process restart | Do not replay prior speech, writes or music automatically. Recover committed action status. |
| Multiple users/devices | No cross-resident calendar reads, tasks, preferences or confirmations. |

## Hive work packages

Assignments below follow existing lanes; coordinate the exact contract and current file ownership before editing shared files. Do not put personal worries, tokens or calendar contents on the bus.

| Lane | Deliverable | Handoff |
|---|---|---|
| Adam — agents and product | Companion orchestrator, prompts, tool proposals, audio arbitration and two-minute demo script | Proposed tool signatures and session events to Szymon; playback/stop expectations to hardware |
| Szymon — backend and app | Resident-scoped execution gateway, reminder reuse, schedule adapter, durable morning items, permissions and app cards | Confirmed request/result shapes and error states to Adam |
| Keanu and Adyan — hardware | Verify Talk/Stop behavior, speaker playback, microphone windows and safety interruption on the actual unit | Exact available device events and measured stop behavior to Adam |

Build sequence:

1. Agree tool/result contract and select labeled demo schedule versus an existing real connector. No external calendar dependency may block the demo.
2. Implement reminder and morning-item execution first, with authorization and idempotency tests.
3. Wire the voice appointment-worry flow to those real writes.
4. Add a single calming audio track, stop and safety preemption.
5. Add family cards and permitted preferences.
6. Run the full hardware flow, record the demo, then consider stretch features.

Keep PRs small and state which scenarios actually ran. Coordinate shared `test-pillow` use on the existing bus before live tests. Do not rewrite Night Watch or migrate the backend for this feature.

## Acceptance criteria

| Scenario | Pass condition |
|---|---|
| Appointment worry | Relevant schedule result is read accurately; confirmation creates one real reminder; app and voice agree on its active/pending state. |
| Midnight boundary | A 3 a.m. request resolves to the correct resident-local date; ambiguous "tomorrow" is clarified. |
| Listen only | A resident asking to be heard creates no task, reminder, family notification or persisted transcript. |
| Morning basket | Item is saved once with explicit visibility and review time; it appears only to authorized readers. |
| Cancel proposal | Declining/remaining silent performs no write. Repeated confirmation or retries do not duplicate it. |
| Calendar failure | Failed lookup cannot produce a claim that there are no appointments. |
| Audio and stop | Playback starts, times out and fades; physical stop takes effect within one second in the bench test. Report actual measured latency. |
| Safety preemption | Existing check-in interrupts music/conversation and retains the original escalation logic. |
| Optional silence | Silence after a settling offer produces quiet, not an assistance alert. |
| Authorization | Another resident's ID, expired proposal or unapproved tool arguments cannot read/write data. |
| Restart and failure | No duplicate reminder, stale confirmation, replayed speech or false success after restart/timeout. |
| Feature disabled | Existing Night Watch and reminder behavior remains available and unchanged. |

Measure request-to-first-audio latency, confirmed-action-to-durable-result latency, stop latency, task completion across scripted runs, duplicate writes and unwanted activations. Record actual results; targets are not achieved measurements. A later opt-in user pilot may ask whether the interaction felt helpful or disruptive. The hackathon demo does not establish improved sleep or reduced medical risk.

## Demo and completion definition

Use a clearly labeled seeded appointment when a real calendar is unavailable. Everything after schedule retrieval must execute for real: confirmed reminder, visible morning item and actual audio playback. Demonstrate a decline or failed save as well as the happy path.

Completion means the primary appointment-worry flow works through the physical voice unit and app, acceptance scenarios pass, limitations are documented, and a local demo recording exists. Code for unrun integrations is not a completed capability.

## Context for the pitch

The team's `product/user-feedback.md` records interest in stories/music after returning to bed, darkness preferences and easier controls. This PRD builds on those observations without assuming every resident wants audio.

Anthropic prioritizes a specific community, firsthand needs, a working product and meaningful Claude use. Microsoft emphasizes measurable usefulness and end-to-end function. Cartesia requires voice to be core. References: [live prizes](https://hive.hackberkeley.org/prizes), [Anthropic announcement](https://cal-hacks-13-0.slack.com/archives/C0C6Z0DP4D8/p1792798675684999), [Microsoft criteria](https://cal-hacks-13-0.slack.com/archives/C0C6X71NCEA/p1792795022826229), [Cartesia announcement](https://cal-hacks-13-0.slack.com/archives/C0C72S4D3LL/p1792816505849089).
