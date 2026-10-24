"""What one check-in reply means (coord/AGENT_FLOW.md section 3).

A judge reads her reply and returns a Verdict; the check-in loop (checkin.py) owns tries, timings
and whether to escalate. `claude_judge` is the live judge. `keyword_judge` is its offline fallback
(no network, error, refusal), so a night check-in never stalls on the API, and the judge in tests.

This module must not import checkin.py: checkin.py runs as __main__, and a second import of it
would create a second, unequal Kind enum.
"""

from __future__ import annotations

import json
import re
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
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


MODEL = "claude-opus-5-5"

SYSTEM = """\
You are the voice of a bedside pillow for an older person who lives alone. It is the middle of the \
night. She got out of bed a while ago and has not come back, so the pillow has just asked her a \
question through a speaker. You get the question and a speech-to-text transcript of her reply, \
which may be mis-transcribed, partial, or in another language.

Decide what her reply means:
- "fine": she is okay (e.g. "I'm fine", "just going to the loo", "yes, back in a minute").
- "confused": she seems disoriented about where she is, what time it is, or what is happening.
- "distress": any sign she is hurt, has fallen, is stuck, unwell, frightened or asking for help. \
When a reply could be distress, choose distress: a wrong alert costs less than a missed fall.
- "unclear": you cannot tell what she means.

Also write `say`, one short line the pillow speaks back, calm and warm, in plain British English:
- fine: a brief reassurance, e.g. "Glad you're okay. Take your time."
- confused: gently reorient her (it's night, she's at home, the light is on by her bed) and end by \
asking if she's alright.
- distress or unclear: an empty string (the pillow uses fixed lines for these).
Never diagnose, name a medical condition, or give medical advice. Keep `say` under 30 words."""

SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["fine", "confused", "distress", "unclear"]},
        "say": {"type": "string"},
    },
    "required": ["kind", "say"],
    "additionalProperties": False,
}

_client = None
_client_lock = threading.Lock()


def _get_client():
    """The shared client. Importing the SDK is the slow part (4-12 s on Windows, measured), so it
    happens here, on first use, rather than at module import: tests run without the SDK at all."""
    global _client
    with _client_lock:
        if _client is None:
            import anthropic

            _client = anthropic.Anthropic(timeout=10.0, max_retries=1)  # short: she's waiting
        return _client


def warm_up() -> None:
    """Get ready before she answers: load the SDK and open a connection to the API.

    Call at startup (pays the SDK import) and when a check-in starts (an idle connection is dropped
    between check-ins). Uses count_tokens, which is free. Never raises: a failed warm-up just means
    the first judgement is slower, and the judge still falls back to keywords if the API is down.
    """
    try:
        _get_client().messages.count_tokens(model=MODEL, messages=[{"role": "user", "content": "warm-up"}])
    except Exception as e:  # noqa: BLE001 - warm-up is best effort
        print(f"  (Claude warm-up failed: {type(e).__name__}: {e})", file=sys.stderr)


def warm_up_in_background() -> None:
    """`warm_up()` without blocking: run it while the pillow is speaking."""
    threading.Thread(target=warm_up, daemon=True).start()


def claude_judge(question: str, text: str) -> Verdict:
    client = _get_client()
    import anthropic  # already loaded by _get_client; needed for the error types below

    try:
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=1024,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=SYSTEM,
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": json.dumps({"question": question, "reply": text})}],
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("refusal")
        data = json.loads(next(b.text for b in response.content if b.type == "text"))
        return Verdict(Kind(data["kind"]), data["say"] or None)
    except (anthropic.APIError, RuntimeError, StopIteration, ValueError, KeyError) as e:
        print(f"  (Claude unavailable: {type(e).__name__}: {e}; using keyword judge)", file=sys.stderr)
        return keyword_judge(question, text)
