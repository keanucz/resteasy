"""Family Liaison: Claude words what the family read and what she hears (coord/AGENT_FLOW.md 3-4).

Night Watch decides WHO is told, on WHICH channel and WHEN (plain code), and hands the Liaison a
step's alerts with fixed, factual messages. Claude may reword each one for its channel (an app
alert, a text, a line read out on a call) using the transcript, and may add one spoken line for
her. It does this through tools, so the ladder itself can't be changed by the model: tool calls
for contacts or channels not in the plan are ignored, and anything it doesn't word keeps the fixed
text. Every result still goes through the Guardian afterwards.

No key, an error or a slow answer (the device is waiting on POST /state) all fall back to the
fixed messages: the Liaison can improve a night, never stall one.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.agents.night_watch import Action, Alert, Say

log = logging.getLogger(__name__)

MODEL = "claude-opus-5-5"
TIMEOUT_S = 5.0  # the pillow's state report is waiting; the fixed messages are fine
SEND_TOOL = "send_family_message"
SPEAK_TOOL = "speak_to_resident"

SYSTEM = """\
You are the family liaison of a bedside pillow for an older person who lives alone. It is night. \
She got out of bed and did not come back, the pillow asked her if she was alright, and now plain \
code has decided which family contacts to alert on which channel. Your only job is the wording.

You get the facts (resident's name, each planned alert with its contact, channel and a factual \
message, recent events, and what the pillow heard her say, which may be mis-transcribed). Call \
`send_family_message` once for EACH planned alert, same contact and channel, with a better message \
for that channel:
- app: one or two short sentences, the headline first ("Mum's been up 25 min and didn't answer").
- sms: under 300 characters, plain, includes when she got up and what she said if anything.
- call: a short script to be read aloud, calm, one fact per sentence.
Keep every fact; add nothing you were not told. Quote what she said if it helps. Never guess a \
cause, never name or hint at a medical condition or diagnosis, never give medical advice. Ask the \
contact to check on her and, if they can't reach her, to go round or call for help. Never say the \
pillow or anyone has called emergency services. Optionally call `speak_to_resident` once with one \
calm, warm line for her in plain American English (under 25 words) saying who is being told. \
Only use the tools; do not reply with text."""

SEND_SCHEMA = {
    "type": "object",
    "properties": {
        "contact": {"type": "string", "description": "exactly as in the plan"},
        "channel": {"type": "string", "enum": ["app", "sms", "call"]},
        "message": {"type": "string"},
    },
    "required": ["contact", "channel", "message"],
    "additionalProperties": False,
}
SPEAK_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
    "additionalProperties": False,
}
TOOLS = [
    {"name": SEND_TOOL, "description": "Send one planned alert with your wording.", "strict": True,
     "input_schema": SEND_SCHEMA},
    {"name": SPEAK_TOOL, "description": "One line the pillow says to her now.", "strict": True,
     "input_schema": SPEAK_SCHEMA},
]
MAX_MESSAGE = 600  # longer wordings keep the fixed text instead


@dataclass(frozen=True)
class Situation:
    """What the Liaison is told: nothing it can act on beyond wording."""

    resident: str
    alerts: list[Alert]  # the step, with fixed factual messages
    events: list[str] = field(default_factory=list)  # recent event types, oldest first
    heard: list[str] = field(default_factory=list)  # what she said at the check-in, if anything

    def prompt(self) -> str:
        return json.dumps({
            "resident": self.resident,
            "planned_alerts": [{"contact": a.contact, "channel": a.channel, "facts": a.message}
                               for a in self.alerts],
            "recent_events": self.events,
            "she_said": self.heard,
        })


def apply_tool_calls(planned: list[Alert], calls: list[Any]) -> list[Action]:
    """Merge Claude's tool calls into the plan: wording for planned (contact, channel) pairs only,
    the fixed text where it gave none, and at most one spoken line."""
    wording: dict[tuple[str, str], str] = {}
    say: str | None = None
    for block in calls:
        if getattr(block, "type", None) != "tool_use":
            continue
        args = block.input if isinstance(block.input, dict) else {}
        if block.name == SEND_TOOL:
            text = str(args.get("message", "")).strip()
            if text and len(text) <= MAX_MESSAGE:
                wording.setdefault((str(args.get("contact")), str(args.get("channel"))), text)
        elif block.name == SPEAK_TOOL and say is None:
            text = str(args.get("text", "")).strip()
            say = text if text and len(text) <= MAX_MESSAGE else None
    out: list[Action] = [Alert(a.contact, a.channel, wording.get((a.contact, a.channel), a.message))
                         for a in planned]
    if say:
        out.append(Say(say))
    return out


class Liaison:
    """Words a step's alerts with Claude; `client` is an AsyncAnthropic (None = fixed text only)."""

    def __init__(self, client: Any = None, *, model: str = MODEL, timeout_s: float = TIMEOUT_S) -> None:
        self.client, self.model, self.timeout_s = client, model, timeout_s

    @classmethod
    def from_api_key(cls, api_key: str) -> Liaison:
        if not api_key:
            return cls(None)
        import anthropic  # slow import, paid once at start-up

        return cls(anthropic.AsyncAnthropic(api_key=api_key, max_retries=0))

    async def compose(self, situation: Situation) -> list[Action]:
        if not situation.alerts:
            return []
        if self.client is None:
            return list(situation.alerts)
        try:
            response = await asyncio.wait_for(
                self.client.beta.messages.create(
                    model=self.model,
                    max_tokens=2048,
                    betas=["server-side-fallback-2026-07-01"],
                    fallbacks="default",
                    system=SYSTEM,
                    tools=TOOLS,
                    tool_choice={"type": "auto"},
                    output_config={"effort": "low"},
                    messages=[{"role": "user", "content": situation.prompt()}],
                ),
                self.timeout_s,
            )
        except Exception as e:  # noqa: BLE001 - key, network, timeout, refusal: the fixed text is safe
            log.warning("Liaison fell back to the fixed messages: %s: %s", type(e).__name__, e)
            return list(situation.alerts)
        if getattr(response, "stop_reason", None) == "refusal":
            return list(situation.alerts)
        return apply_tool_calls(situation.alerts, list(response.content))
