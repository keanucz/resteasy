# /// script
# requires-python = ">=3.12"
# dependencies = ["anthropic", "httpx>=0.27", "numpy>=1.26", "sounddevice>=0.4", "websockets>=14"]
# ///
"""The night check-in conversation: ask, listen, retry, warn, then escalate or stand down.

Plain code (coord/AGENT_FLOW.md section 3): this owns the tries, the timings and when to escalate.
A `judge` reads each reply: Claude (voice/judge.py) in the live run, with the keyword `classify`
below as its offline fallback and as the judge in tests.

    uv run voice/checkin.py --contact Sarah     # needs CARTESIA_API_KEY and ANTHROPIC_API_KEY
    uv run voice/checkin.py --keywords          # no Claude, keyword judge only

Rules:
- Distress ("I've fallen", "help") escalates at once, and she is told so.
- Silence or speech we can't make out: up to `max_tries` asks, each a little louder.
- Confused ("where am I?"): one reorienting answer, then the tries start again (once only).
- Before escalating she is warned and has `cancel_s` to say she's fine.
- Clear "I'm fine" at any point stands down.
- The distress and warning lines are fixed here; a judge may only word the fine and reorient lines.
"""

from __future__ import annotations

import argparse
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum


class Kind(StrEnum):
    FINE = "fine"
    CONFUSED = "confused"
    DISTRESS = "distress"
    UNCLEAR = "unclear"  # she spoke, but we couldn't make out an answer
    SILENT = "silent"


@dataclass
class Verdict:
    kind: Kind
    say: str | None = None  # optional line to speak back (fine / confused only)


Judge = Callable[[str, str], Verdict]  # judge(question asked, her reply text) -> Verdict

_DISTRESS = re.compile(
    r"\b(fallen|fell|fall|help|hurt|hurts|pain|can'?t get up|cannot get up|stuck|bleeding|ambulance|"
    r"not (?:ok|okay|fine|alright|all right|good))\b")
_CONFUSED = re.compile(r"\b(where am i|where is|what time|who are you|what'?s (?:happening|going on)|confused|lost)\b")
_FINE = re.compile(r"\b(fine|ok|okay|alright|all right|good|yes|yeah|yep|toilet|loo|bathroom|back to bed|i'?m up)\b")


def classify(text: str, spoke: bool) -> Kind:
    """Keyword judge. Distress wins over everything, then confusion, then fine."""
    t = text.lower().replace("’", "'")
    if not t:
        return Kind.UNCLEAR if spoke else Kind.SILENT
    if _DISTRESS.search(t):
        return Kind.DISTRESS
    if _CONFUSED.search(t):
        return Kind.CONFUSED
    if _FINE.search(t):
        return Kind.FINE
    return Kind.UNCLEAR


def keyword_judge(_question: str, text: str) -> Verdict:
    return Verdict(classify(text, True))


@dataclass
class Outcome:
    escalate: bool
    reason: str  # one plain sentence for the family message, never a diagnosis
    heard: list[str] = field(default_factory=list)


Speak = Callable[..., None]  # speak(text, volume=...)
Listen = Callable[..., object]  # listen(no_answer_s=...) -> object with .text and .spoke

VOLUMES = (1.0, 1.3, 1.6, 1.8, 2.0)  # a little louder each try (voice.speak's 0.5-2.0 scale)
_MAX_SAY = 220  # longer judge lines are ignored in favour of the fixed ones


def _usable(say: str | None) -> str | None:
    return say.strip() if say and say.strip() and len(say) <= _MAX_SAY else None


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
) -> Outcome:
    heard: list[str] = []
    ever_spoke = False
    reoriented = False

    def ask(prompt: str, volume: float, wait_s: float) -> Verdict:
        nonlocal ever_spoke
        speak(prompt, volume=volume)
        reply = listen(no_answer_s=wait_s)
        ever_spoke = ever_spoke or reply.spoke
        if reply.text:
            heard.append(reply.text)
            verdict = judge(prompt, reply.text)
        else:
            verdict = Verdict(Kind.UNCLEAR if reply.spoke else Kind.SILENT)
        log(f"{prompt!r} -> {verdict.kind}: {reply.text!r}")
        return verdict

    def distress() -> Outcome:
        speak(f"Okay. I'm getting {contact} for you now. Help is coming.", volume=1.3)
        return Outcome(True, f'She said: "{heard[-1]}"', heard)

    def fine(v: Verdict) -> Outcome:
        speak(_usable(v.say) or "Glad you're okay. Take your time.")
        return Outcome(False, "She said she was fine.", heard)

    prompt, attempt = "Are you alright?", 0
    while attempt < max_tries:
        v = ask(prompt, VOLUMES[min(attempt, len(VOLUMES) - 1)], no_answer_s)
        attempt += 1
        if v.kind is Kind.DISTRESS:
            return distress()
        if v.kind is Kind.FINE:
            return fine(v)
        if v.kind is Kind.CONFUSED and not reoriented:
            reoriented, attempt = True, 0
            prompt = _usable(v.say) or ("It's the middle of the night and you're at home. "
                                        "The light's on by your bed.")
            if not prompt.rstrip().endswith("?"):
                prompt += " Are you alright?"
        elif v.kind in (Kind.UNCLEAR, Kind.CONFUSED):
            prompt = "Sorry, I didn't quite catch that. Are you alright?"
        else:
            prompt = "I just want to check you're okay. Are you alright?"

    v = ask(f"I haven't been able to hear you, so I'm going to let {contact} know to check on you. "
            "If you're okay, just say I'm fine.", 2.0, cancel_s)
    if v.kind is Kind.FINE:
        return fine(v)
    if v.kind is Kind.DISTRESS:
        return distress()
    speak(f"Okay, I'm letting {contact} know now.", volume=1.3)
    if ever_spoke:
        return Outcome(True, "She answered but we couldn't understand her.", heard)
    return Outcome(True, "She didn't answer.", heard)


def main() -> None:
    import voice  # audio + Cartesia only needed for the live run

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--contact", default="your family", help="who gets alerted, e.g. Sarah")
    parser.add_argument("--tries", type=int, default=3)
    parser.add_argument("--no-answer-s", type=float, default=8.0)
    parser.add_argument("--cancel-s", type=float, default=15.0)
    parser.add_argument("--keywords", action="store_true", help="judge replies by keywords, not Claude")
    args = parser.parse_args()

    if args.keywords:
        judge = keyword_judge
    else:
        from judge import claude_judge
        judge = claude_judge

    out = run_checkin(voice.speak, voice.listen, judge=judge, contact=args.contact, max_tries=args.tries,
                      no_answer_s=args.no_answer_s, cancel_s=args.cancel_s, log=print)
    print(f"\n{'ESCALATE' if out.escalate else 'STAND DOWN'}: {out.reason}")


if __name__ == "__main__":
    main()
