"""Claude reads one check-in reply and says what it means (coord/AGENT_FLOW.md section 3).

Claude only judges and words a short reply; the check-in loop (checkin.py) owns tries, timings and
whether to escalate. If Claude can't answer (no network, error, refusal) the keyword judge decides,
so a night check-in never stalls on the API.
"""

from __future__ import annotations

import json
import sys

import anthropic

from checkin import Kind, Verdict, keyword_judge

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

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:  # short timeout: she is waiting for an answer in the dark
        _client = anthropic.Anthropic(timeout=10.0, max_retries=1)
    return _client


def claude_judge(question: str, text: str) -> Verdict:
    try:
        response = _get_client().beta.messages.create(
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
