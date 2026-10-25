# /// script
# requires-python = ">=3.12"
# dependencies = ["anthropic>=2.3","httpx>=0.27", "numpy>=1.26", "sounddevice>=0.4", "websockets>=14"]
# ///
"""The night check-in conversation: ask, listen, retry, warn, then escalate or stand down.

Plain code (coord/AGENT_FLOW.md section 3): this owns the tries, the timings and when to escalate.
A judge (voice/judge.py) reads each reply: Claude in the live run, keywords offline and in tests.

    uv run voice/checkin.py --contact Sarah     # needs CARTESIA_API_KEY and ANTHROPIC_API_KEY
    uv run voice/checkin.py --keywords          # no Claude, keyword judge only

Rules:
- Distress ("I've fallen", "help") escalates at once, and she is told so.
- Silence or speech we can't make out: up to `max_tries` asks, each a little louder.
- Confused ("where am I?"): reorient her each time; the first time also restarts the tries.
- Before escalating she is warned and has `cancel_s` to say she's fine; only an explicit "I'm fine"
  cancels then ("yes" could be agreeing to the call).
- Clear "I'm fine" at any point stands down.
- If the check-in itself fails (no network, no mic, a crash), it escalates: never fail silent.
- The distress, warning and reorient lines are fixed here; a judge may only word the fine line.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass, field

from judge import Judge, Kind, Verdict, keyword_judge, said_fine


@dataclass
class Outcome:
    escalate: bool
    reason: str  # one plain sentence for the family message, never a diagnosis
    heard: list[str] = field(default_factory=list)
    distress: bool = False  # she sounded in trouble: the server calls family at once


Speak = Callable[..., None]  # speak(text, volume=...)
Listen = Callable[..., object]  # listen(no_answer_s=...) -> object with .text and .spoke

VOLUMES = (1.0, 1.3, 1.6, 1.8, 2.0)  # a little louder each try (voice.speak's 0.5-2.0 scale)
_MAX_SAY = 220  # longer judge lines are ignored in favour of the fixed ones
_REORIENT = "It's the middle of the night and you're at home. The light's on by your bed."


def _usable(say: str | None) -> str | None:
    return say.strip() if say and say.strip() and len(say) <= _MAX_SAY else None


STOPPED_REASON = "She pressed I'm fine."


class _Stopped(Exception):
    """She pressed "I'm fine" during the check-in."""


def run_checkin(
    speak: Speak,
    listen: Listen,
    *,
    judge: Judge = keyword_judge,
    contact: str = "your family",
    max_tries: int = 3,
    no_answer_s: float = 8.0,
    cancel_s: float = 15.0,
    log: Callable[[str], None] = lambda _: None,
    should_stop: Callable[[], bool] = lambda: False,
) -> Outcome:
    """`should_stop`: she pressed "I'm fine" on the pad (the server already knows); checked before
    each question, so the pillow stops asking."""
    heard: list[str] = []
    seen: set[Kind] = set()
    reoriented = False

    def ask(prompt: str, volume: float, wait_s: float) -> Verdict:
        if should_stop():
            raise _Stopped
        speak(prompt, volume=volume)
        reply = listen(no_answer_s=wait_s)
        if reply.text:
            heard.append(reply.text)
            verdict = judge(prompt, reply.text)
        else:
            verdict = Verdict(Kind.UNCLEAR if reply.spoke else Kind.SILENT)
        seen.add(verdict.kind)
        log(f"{prompt!r} -> {verdict.kind}: {reply.text!r}")
        return verdict

    def distress() -> Outcome:
        speak(f"Okay. I'm getting {contact} for you now. Help is coming.", volume=1.3)
        return Outcome(True, f'She said: "{heard[-1]}"', heard, distress=True)

    def fine(v: Verdict) -> Outcome:
        speak(_usable(v.say) or "Glad you're okay. Take your time.")
        return Outcome(False, "She said she was fine.", heard)

    def conversation() -> Outcome:
        nonlocal reoriented
        prompt, attempt = "Are you alright?", 0
        while attempt < max_tries:
            v = ask(prompt, VOLUMES[min(attempt, len(VOLUMES) - 1)], no_answer_s)
            attempt += 1
            if v.kind is Kind.DISTRESS:
                return distress()
            if v.kind is Kind.FINE:
                return fine(v)
            if v.kind is Kind.CONFUSED:
                if not reoriented:
                    reoriented, attempt = True, 0
                prompt = f"{_REORIENT} Are you alright?"
            elif v.kind is Kind.UNCLEAR:
                prompt = "Sorry, I didn't quite catch that. Are you alright?"
            else:
                prompt = "I just want to check you're okay. Are you alright?"

        v = ask(f"I haven't been able to hear you, so I'm going to let {contact} know to check on you. "
                "If you're okay, just say I'm fine.", 2.0, cancel_s)
        if v.kind is Kind.FINE and said_fine(heard[-1]):
            return fine(v)
        if v.kind is Kind.DISTRESS:
            return distress()
        speak(f"Okay, I'm letting {contact} know now.", volume=1.3)
        if Kind.CONFUSED in seen:
            return Outcome(True, "She answered but seemed confused about where she was.", heard)
        if Kind.UNCLEAR in seen:
            return Outcome(True, "She answered but we couldn't understand her.", heard)
        return Outcome(True, "She didn't answer.", heard)

    try:
        return conversation()
    except _Stopped:
        log("stopped: she pressed I'm fine")
        speak("Okay. Glad you're okay.")
        return Outcome(False, STOPPED_REASON, heard)
    except Exception as e:  # noqa: BLE001 - speaker, mic, network or judge: fail toward escalation
        log(f"check-in failed: {type(e).__name__}: {e}")
        return Outcome(True, "The pillow's check-in could not run, so we couldn't ask her.", heard)


ALERT_ASK_EVERY_S = 30.0  # while family are being alerted, the pillow keeps offering her a way out
ALERT_LINE = "I've let {contact} know. If you're okay, just say I'm fine."
ALERT_FINE_LINE = "Okay. I'll tell {contact} you're fine."


def ask_after_alert(speak: Speak, listen: Listen, *, contact: str = "your family", no_answer_s: float = 10.0,
                    log: Callable[[str], None] = lambda _: None) -> bool:
    """Once the alert has gone out: ask once, and True only for an explicit "I'm fine" (the caller
    then stops the alert). "Yes", silence, a mumble or distress leave the ladder running."""
    speak(ALERT_LINE.format(contact=contact), volume=1.6)
    reply = listen(no_answer_s=no_answer_s)
    text = getattr(reply, "text", "") or ""
    log(f"after the alert she said {text!r}" if text else "after the alert: no answer")
    if not said_fine(text):
        return False
    speak(ALERT_FINE_LINE.format(contact=contact))
    return True


def main() -> None:
    import voice  # audio + Cartesia only needed for the live run

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--contact", default="your family", help="who gets alerted, e.g. Sarah")
    parser.add_argument("--tries", type=int, default=3)
    parser.add_argument("--no-answer-s", type=float, default=8.0)
    parser.add_argument("--cancel-s", type=float, default=15.0)
    parser.add_argument("--keywords", action="store_true", help="judge replies by keywords, not Claude")
    args = parser.parse_args()
    voice._key()  # exits now, not mid check-in, if CARTESIA_API_KEY is missing

    if args.keywords:
        judge = keyword_judge
    else:
        from judge import claude_judge, warm_up_in_background
        warm_up_in_background()  # loads the SDK while the first question is being spoken
        judge = claude_judge

    out = run_checkin(voice.speak, voice.listen, judge=judge, contact=args.contact, max_tries=args.tries,
                      no_answer_s=args.no_answer_s, cancel_s=args.cancel_s, log=print)
    print(f"\n{'ESCALATE' if out.escalate else 'STAND DOWN'}: {out.reason}")


if __name__ == "__main__":
    main()
