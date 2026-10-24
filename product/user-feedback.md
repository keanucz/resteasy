# User feedback

Real reactions to the idea, newest first. Paraphrased; names of private people left out.

## Sat 24 Oct, Keanu's mum, written review of the product description

She edited the shared product doc (Drive version history: two anonymous revisions, 11:16 and 12:05
UTC) and highlighted her additions, then added more by text. Paraphrased; her own words in quotes.

**Liked:** the goodnight message and bedtime story, the path light ("Wow, this sounds cool!" for
both), the check-in (chime, then "Are you okay?": "I like this"), the 4am breathing light ("Good
idea!").

**Questions she raised:**

1. **Full darkness.** Some people can only sleep in a fully dark room: what about the base's soft
   light and the glow on the family's pillow? Her own fix, by text: the light stays off unless she
   asks for it out loud, "I want light" / "I want to see", because feeling for a lamp switch in the
   dark is hard with arthritic fingers. Alexa can already switch lights by voice; the point is
   that the pillow does it, with nothing else in the room.
2. **Quiet hours read as "no alerts".** She asked whether quiet hours 22:00-07:00 stop the family
   being told at 2am in an emergency. In our design that window is when the pillow *watches*; each
   contact's own do-not-disturb hours are separate. The word "quiet" says the opposite.
3. **Sensing with the face up.** How does it know her head is there if she doesn't breathe into the
   pillow? (Answer: head warmth is the main signal; humidity only backs it up.)
4. **Family-voice stories.** Only with that person's permission, and the recording must never leak
   or be hackable; she mentions daytime visitors (nurses, cleaners) and the recording.

**Changes she made to the flow:**

5. After a return to bed, and after an "I'm fine", play calm music or a story automatically,
   "as that is needed for an old person to be able to sleep back again". We currently stay silent.
6. 4am: a *breathing meditation*, not just a breathing light.
7. Third contact: not a neighbour by default, but "a very good, close friend who signs up for it".
8. "It is a direct connection only to" the family's app and pillow: privacy as a selling point.
9. Buttons glow softly at night and differ by shape as well as colour (no glasses at night):
   Talk = white rectangle, pillow-shaped; I'm fine = green round; Call family = red round.
10. **Buttons off the lamp.** Put the three buttons on a remote, or on a switch unit on a cable
    like an old bedside-lamp switch, so pressing a big button in the dark doesn't push the whole
    base off the bedside table. Keep the remote in the bedside drawer, not loose: a remote that
    falls to the floor at night is lost. (Ours today: a remote whose buttons are hard to press, and
    a sponsor's mini keyboard whose keys press too easily. Neither is right for arthritic fingers.)
    Her pitch line: "a basic prototype; with more resources the next stage sources proper big
    buttons. Here we demonstrate the principle."

**Pitch and market (sections she wrote):**

11. **Sleep companion first, safety as the bonus.** Older people's nights are broken into two or
    three pieces (for men often prostate trips); helping them get back to sleep is the everyday
    value, and it keeps us clear of medical claims.
12. **Not a medical device:** a clear disclaimer, "Lifestyle Aid" / comfort product, no substitute
    for a doctor, certified monitors or prescribed medication.
13. **The gap filler:** between wealthy pensioners' smartwatches and monitors linked to health
    professionals, and having no safety device at all. A watch in bed feels unnatural; a pillow
    is already part of a good night.
14. **Looks like a normal pillow and bedside lamp**, not a scary device, for people for whom even a
    smartphone or Alexa is too fiddly or alien. Choice of cover colour so it becomes "THE pillow".
    Washable, allergy-proof textiles; no battery, nothing to charge or wear, no camera.
15. **Price: one-off, no subscription.** They bought it; nothing like a nurse call centre justifies
    a fee. Instalments are a trap (who pays if she dies or moves into a care home?). The one fee
    that could make sense: a bundled minimal data plan for a home with only a landline. Open
    question for us: what does the pillow need in a home with no broadband?
16. **A cheaper offline "Value" version:** no alerts, just the bedtime routine, light, music and
    stories (including ones family record in their own voice; mind copyright).
17. **A gift:** Christmas and birthday covers, "a headache for families what to buy" for a
    grandma. Our pod fits any pillow, so covers are cheap variants.
18. **A joke for the judges:** mirror every step for students, a *wake-up* pillow that buzzes,
    plays hard rock and motivational lines, and alerts the (already awake) grandparents to phone
    the grandson whose head is still on it; it stops when he says "I'm already on my feet".

She also pasted a general web answer on why older adults sleep badly (body clock, lighter sleep,
less melatonin, nocturia, pain, apnea, restless legs, dementia/Parkinson's, medications, alcohol,
naps). Useful as a checklist; cite `academic-evidence.md`, not it. Questions 1-10 of our list are
still unanswered.

**What it means per lane (suggestions, not decisions):**

| Lane | Implication |
|---|---|
| Pitch | Lead with "helps her get back to sleep; tells family only when something's wrong". Not-a-medical-device line. One-off price, gift angle, the wake-up-pillow joke if time allows |
| Agents (Adam) | Voice "light on" / "light off" while Talk is held (no wake word, so the mic promise holds). Calm story or music after `bed_return` and after FINE; a breathing meditation |
| Backend + app (Szymon) | Rename "quiet hours" (e.g. "night watch hours") and explain contacts' do-not-disturb separately. Third contact = opt-in friend. A setting for the light: off unless asked |
| Hardware (Keanu, Adyan) | Glowing buttons distinguishable by shape, on a corded switch unit or remote rather than the base; base light off by default |

## Sat 24 Oct, Szymon and Adam pitching to older people on the street

They liked it. Asked for: reminders when they wake, for medication or to call someone.

## Sat 24 Oct, Keanu's mum (texted after hearing the pitch)

Who she is for us: an adult child of older parents (our buyer), and someone who herself wakes too
early and struggles to get back to sleep (a second user of the calm features).

**What she understood, unprompted:** "a pillow for grandmas and grandpas that they can talk to, but
that also detects if you've been to the toilet during the night for too long, suspects you may
have fallen and need help, and sends that signal to the phone number of their relatives." That
is our core flow, so the one-line pitch is landing.

**Points she raised:**

1. **Competitor she knows: health smartwatches.** A family friend wears one that measures blood
   oxygen and pulse, alarms if the pulse is irregular or stops, and has an easy button to phone a
   call centre; pricier models add blood pressure and ECG.
2. **Her positioning for us: a low-cost gap filler for the night.** People may not want to sleep
   wearing a watch (not relaxing), and an Apple or Samsung watch is too expensive and "too modern"
   for many older people. *Matches our evidence: only 18% of medical-alert users wear theirs all the
   time, and watches are on the charger at night.*
3. **Feature: relaxing bedtime stories, "zen stories".** Important to her personally for falling
   back asleep after waking too early.
4. **Talk to it like a simpler, cheaper Alexa:** "pillow, play relaxing music" / "tell me a story".
5. **Make the pillow easily washable.**

**What it means per lane (suggestions, not decisions):**

| Lane | Implication |
|---|---|
| Adam (pitch) | Lead with "the night gap: watches come off at bedtime"; position against health watches and pendants on price and comfort, not features. Add the smartwatch row to the competitor table |
| Adyan (agents) | Settle agent: on-request stories and calm music, plus an "early waking" path (awake before ~05:00 and restless → offer a back-to-sleep story). A strong Cartesia voice moment. Keep it secondary to Night Watch |
| Szymon (backend) | Alerts go to relatives' **phone numbers** (SMS/call), not only the app: contacts need a phone field |
| Keanu (hardware) | Washable by design: all electronics in one removable pod (3D-printed, slides out through the cover zip), nothing sewn in, no battery inside. Say "unzip, pull the pod, wash the pillow" in the pitch |
