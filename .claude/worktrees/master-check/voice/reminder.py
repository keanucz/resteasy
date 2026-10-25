"""Say one due reminder (the Routine agent, backend/app/agents/reminders.py) and hear how it went.

The server owns the schedule and the retries; this only speaks the line it was given, and, for a
reminder that asks her to confirm, listens once and reads the reply with a judge (Claude in the live
run, keywords offline and in tests). The outcome goes back to POST .../reminders/{id}/result:

    announced   spoken (a reminder that doesn't ask)
    done        she said she has done it
    not_done    not yet, or we couldn't tell: the server asks again later (once)
    no_answer   silence, or the pillow couldn't ask (no network, no mic, a crash)
    distress    she sounded hurt or asked for help: the server escalates through Night Watch
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from judge import Answer, ReminderJudge, keyword_reminder_judge

LEAD_IN_S = 2.0  # the buzzer sounds first (queued by the server): let it finish
VOLUME = 1.5  # daytime, maybe across the room: a little louder than a night check-in
ASK = "Have you done that yet?"
LINES = {
    Answer.DONE: "Lovely, thank you.",
    Answer.NOT_YET: "Okay, no rush.",
    Answer.UNCLEAR: "Sorry, I didn't quite catch that.",
    Answer.DISTRESS: "Okay. I'm letting your family know now. Help is coming.",
}
OUTCOMES = {Answer.DONE: "done", Answer.NOT_YET: "not_done", Answer.UNCLEAR: "not_done",
            Answer.DISTRESS: "distress"}


@dataclass
class ReminderOutcome:
    outcome: str
    reply: str | None = None


def run_reminder(
    speak: Callable[..., None],
    listen: Callable[..., object],
    *,
    text: str,
    confirm: bool,
    judge: ReminderJudge = keyword_reminder_judge,
    no_answer_s: float = 10.0,
    sleep: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] = lambda _: None,
) -> ReminderOutcome:
    try:
        sleep(LEAD_IN_S)
        if not confirm:
            speak(text, volume=VOLUME)
            return ReminderOutcome("announced")
        speak(f"{text} {ASK}", volume=VOLUME)
        reply = listen(no_answer_s=no_answer_s)
        if not reply.text:
            log(f"{text!r} -> {'mumble' if reply.spoke else 'silence'}")
            return ReminderOutcome("not_done" if reply.spoke else "no_answer")
        answer = judge(text, reply.text)
        log(f"{text!r} -> {answer}: {reply.text!r}")
        speak(LINES[answer], volume=VOLUME)
        return ReminderOutcome(OUTCOMES[answer], reply.text[:300])
    except Exception as e:  # noqa: BLE001 - speaker, mic, network or judge: the server asks again
        log(f"reminder failed: {type(e).__name__}: {e}")
        return ReminderOutcome("no_answer")
