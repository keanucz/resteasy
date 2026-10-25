# /// script
# requires-python = ">=3.12"
# dependencies = ["uagents==0.25.5", "uagents-core==0.4.9", "anthropic>=2.3", "httpx>=0.27"]
# ///
"""A family member's agent: one per person who looks after her, talked to in ASI:One.

A uAgent on Agentverse (Agent Chat Protocol, mailbox) that speaks for ONE family member (CONTACT_ID)
about ONE pillow. It is their agent, not the pillow's: it remembers what they tell it ("I'm in Denver
Thu-Sun") and answers the pillow's coordinator for them each evening (coordinator_agent.py).

    "How was Mum's night?"                       -> GET /night, shown as a card
    "Send Mum a goodnight"                       -> a form card, then POST /goodnight
    "I'm away Thu-Sun, make sure Mum's covered"  -> a plan (away dates, goodnights, settings)
                                                    shown as a Confirm / Cancel card

Goals become plans: Claude calls several tools at once, but every tool that changes something is
only queued. The person sees the whole plan and confirms it; only then does plain code carry the
steps out, through the backend and its Guardian. Reads answer straight away.

    export AGENT_SEED='<private phrase>' CONTACT_ID=<contacts.id> CONTACT_NAME=Sarah
    export ANTHROPIC_API_KEY=...  CHECKIN_TOKEN=<backend/.env>  COORDINATOR_ADDRESS=agent1q...
    uv run agents/fetch/family_agent.py
See agents/fetch/README.md.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

import anthropic  # imported at start-up: it takes 4-12 s on Windows, too slow for a first reply
import httpx
from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    TextContent,
    chat_protocol_spec,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cards  # noqa: E402
from agentverse import start_connect  # noqa: E402
from models import AvailabilityReply, AvailabilityRequest, JoinRoster, roster_protocol  # noqa: E402

SERVER = os.environ.get("PILLOW_SERVER", "https://pillow.keanuc.net").rstrip("/")
PILLOW_ID = os.environ.get("PILLOW_ID", "mum")
TOKEN = os.environ.get("CHECKIN_TOKEN", "").strip()
CONTACT_ID = os.environ.get("CONTACT_ID", "").strip()
CONTACT_NAME = os.environ.get("CONTACT_NAME", "").strip() or "their family member"
RESIDENT = os.environ.get("RESIDENT_NAME", "Mum")
COORDINATOR = os.environ.get("COORDINATOR_ADDRESS", "").strip()
TZ = ZoneInfo(os.environ.get("RESIDENT_TZ", "America/Los_Angeles"))
MODEL = "claude-opus-5-5"
HISTORY_TURNS = 6
HERE = Path(__file__).resolve().parent
PORT = int(os.environ.get("AGENT_PORT", "8001"))
_slug = re.sub(r"[^a-z0-9]+", "-", CONTACT_NAME.lower()).strip("-") or "family"

agent = Agent(
    name=os.environ.get("AGENT_NAME") or f"pillow-family-{_slug}",
    seed=os.environ.get("AGENT_SEED") or sys.exit("AGENT_SEED is not set"),
    port=PORT,
    # Agentverse mailbox in production; AGENT_ENDPOINT (http://127.0.0.1:<port>/submit) for local tests
    mailbox=not os.environ.get("AGENT_ENDPOINT"),
    endpoint=[os.environ["AGENT_ENDPOINT"]] if os.environ.get("AGENT_ENDPOINT") else None,
    publish_agent_details=True,
    readme_path=str(HERE / "README.md"),
    description=f"{CONTACT_NAME}'s agent for {RESIDENT}'s bedside pillow: how her night went, goodnight "
    "messages, settings, and whether they can be called first tonight.",
)
chat = Protocol(spec=chat_protocol_spec)
roster = roster_protocol()

# Tools that change something: queued into a plan the person confirms, never run by Claude directly
WRITE_TOOLS = {"set_settings", "send_goodnight", "set_away", "clear_away"}
YES = re.compile(r"^\s*(yes|yep|yeah|confirm(ed)?|ok(ay)?|go ahead|do it|sounds good)\b", re.I)
NO = re.compile(r"^\s*(no|nope|cancel|stop|don'?t)\b", re.I)

SYSTEM = """\
You are {name}'s agent for the bedside pillow that watches over {resident}, an older person who lives \
alone (pillow id {pillow}). You talk only to {name}, in a chat. Today is {today} ({tz}).

Read tools answer at once: use them for every factual question, never answer from memory about the \
night. Change tools (set_settings, send_goodnight, set_away, clear_away) do NOT run when \
you call them: they are queued into a plan that {name} sees as a Confirm / Cancel card. When {name} \
gives you a goal ("I'm away Thu-Sun, make sure Mum's covered", "keep a closer eye this week"), work out \
every step it needs and call all the change tools in one go, then describe the plan in 1-3 sentences \
and say nothing changes until they confirm. Ask a short question instead only if a step really needs \
words or a time only they can give (e.g. the goodnight text). If they want to send a goodnight but \
haven't given the words, call show_goodnight_form.

Being away: set_away marks nights when {name} can't be called first (from_date = first night, \
until_date = last night, both YYYY-MM-DD). Each evening the pillow's coordinator asks this agent, and on \
those nights the other family members are tried first; everyone is still alerted in the end.

Rules: keep replies short, warm and plain, 1-4 sentences, no bullet lists unless asked. Report only what \
tools return; never guess why something happened; never name or hint at a medical condition; never \
give medical advice; never claim anyone called emergency services. If asked something the tools can't \
do, say so in one sentence."""


def _strict(props: dict[str, Any] | None = None, required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": props or {}, "required": required or list(props or {}),
            "additionalProperties": False}


TOOLS: list[dict[str, Any]] = [
    {"name": "get_status", "description": "Live state now: is her head on the pillow, the night state "
     "(awake/in_bed/up/check_in/escalating), room light and temperature.", "strict": True,
     "input_schema": _strict()},
    {"name": "get_night", "description": "Last night: summary (lay down, asleep, trips with times and "
     "lengths, check-ins, alerts, who acknowledged, restless spells, anything unusual), the latest Morning "
     "Brief note if one exists, and current settings. The person also sees it as a card.", "strict": True,
     "input_schema": _strict()},
    {"name": "get_agent_log", "description": "What the pillow's agents did last night, step by step, with "
     "the Guardian's allowed/blocked verdicts.", "strict": True, "input_schema": _strict()},
    {"name": "get_roster", "description": "Who looks after her, in alert order, and who is on call "
     "(tried first) right now.", "strict": True, "input_schema": _strict()},
    {"name": "get_my_availability", "description": f"The away dates {CONTACT_NAME} has given this agent.",
     "strict": True, "input_schema": _strict()},
    {"name": "show_goodnight_form", "description": "Show a form where they type a goodnight message.",
     "strict": True, "input_schema": _strict()},
    {"name": "send_goodnight", "description": "QUEUED for approval. A goodnight message in the sender's "
     "exact words; the pillow plays it when she next lies down.", "strict": True,
     "input_schema": _strict({"message": {"type": "string"},
                              "from_name": {"type": "string", "description": "who it's from"}})},
    {"name": "set_settings", "description": "QUEUED for approval. Change her quiet hours (HH:MM, when the "
     "pillow watches) and/or the minutes before it checks in after she gets up (10-30). Null = unchanged.",
     "strict": True, "input_schema": _strict({
         "quiet_start": {"type": ["string", "null"]}, "quiet_end": {"type": ["string", "null"]},
         "checkin_timeout_min": {"type": ["integer", "null"]}})},
    {"name": "set_away", "description": f"QUEUED for approval. Nights {CONTACT_NAME} can't be called first.",
     "strict": True, "input_schema": _strict({
         "from_date": {"type": "string"}, "until_date": {"type": "string"},
         "note": {"type": "string", "description": "a few words, e.g. 'in Denver'"}})},
    {"name": "clear_away", "description": f"QUEUED for approval. Forget all of {CONTACT_NAME}'s away dates.",
     "strict": True, "input_schema": _strict()},
]

def _day(iso: str) -> str:
    try:
        return date.fromisoformat(iso).strftime("%a %d %b")
    except ValueError:
        return iso


def describe(name: str, args: dict[str, Any]) -> tuple[str, str]:
    """One plan step as a (label, value) row of the review card. Plain code, not Claude's words."""
    if name == "set_settings":
        parts = []
        if args.get("quiet_start") or args.get("quiet_end"):
            parts.append(f"watches {args.get('quiet_start') or '?'}-{args.get('quiet_end') or '?'}")
        if args.get("checkin_timeout_min") is not None:
            parts.append(f"checks in after {args['checkin_timeout_min']} min up")
        return "Pillow settings", ", ".join(parts) or "no change"
    if name == "send_goodnight":
        return f"Goodnight from {args.get('from_name')}", f"\"{args.get('message')}\""
    if name == "set_away":
        return f"{CONTACT_NAME} away", (f"{_day(args['from_date'])} to {_day(args['until_date'])} "
                                       f"({args.get('note') or 'away'}): others called first those nights")
    if name == "clear_away":
        return f"{CONTACT_NAME} away", "forget all away dates"
    return name, json.dumps(args)


def _away(storage: Any) -> list[dict[str, str]]:
    return storage.get("away") or []


def away_on(storage: Any, night: str) -> dict[str, str] | None:
    """The away entry covering `night` (YYYY-MM-DD), if any. Plain code: the roster's answer."""
    return next((a for a in _away(storage) if a["from"] <= night <= a["until"]), None)


async def call_tool(http: httpx.AsyncClient, storage: Any, name: str, args: dict[str, Any]) -> Any:
    base = f"{SERVER}/api/pillows/{PILLOW_ID}"
    auth = {"Authorization": f"Bearer {TOKEN}"}
    if name == "get_status":
        r = await http.get(f"{base}/state")
        r.raise_for_status()
        s = r.json()
        return {k: s.get(k) for k in ("night_state", "head_on", "light", "temp_c", "humidity", "state_since")}
    if name == "get_night":
        r = await http.get(f"{base}/night")
        r.raise_for_status()
        night = r.json()
        out = {"resident": night["resident"], "window": [night["window_start"], night["window_end"]],
               "summary": night["summary"], "settings": night["settings"]}
        b = await http.get(f"{base}/brief")
        if b.status_code == 200:
            out["morning_brief"] = b.json()
        return out
    if name == "get_agent_log":
        r = await http.get(f"{base}/night")
        r.raise_for_status()
        return [{k: row.get(k) for k in ("ts", "agent", "intent", "guardian", "reason")}
                for row in r.json()["agent_log"]][-40:]
    if name == "get_roster":
        r = await http.get(f"{base}/roster", headers=auth)
        r.raise_for_status()
        keys = ("name", "on_call", "quiet_start", "quiet_end")
        return [{k: c[k] for k in keys} for c in r.json()["contacts"]]
    if name == "get_my_availability":
        return {"away": _away(storage)}
    if name == "send_goodnight":
        r = await http.post(f"{base}/goodnight", json=args)
        if r.status_code == 422:
            return {"blocked": r.json().get("detail")}
        r.raise_for_status()
        return {"queued": r.json()}
    if name == "set_settings":
        patch = {k: v for k, v in args.items() if v is not None}
        if not patch:
            return {"error": "nothing to change"}
        r = await http.patch(f"{base}/settings", json=patch, headers=auth)
        r.raise_for_status()
        return r.json()
    if name == "set_away":
        for key in ("from_date", "until_date"):
            date.fromisoformat(args[key])  # a bad date raises, and Claude is told
        entry = {"from": args["from_date"], "until": args["until_date"], "note": args.get("note") or "away"}
        storage.set("away", [*_away(storage), entry])
        return {"saved": entry}
    if name == "clear_away":
        storage.set("away", [])
        return {"cleared": True}
    return {"error": f"unknown tool {name}"}


class Turn:
    """What one Claude turn produced: the text, change steps waiting for approval, and which card."""

    def __init__(self) -> None:
        self.text = ""
        self.steps: list[dict[str, Any]] = []
        self.night: dict[str, Any] | None = None
        self.form = False


async def answer(storage: Any, history: list[dict[str, Any]], text: str) -> Turn:
    """One Claude tool loop: reads run now, change tools are collected into a plan."""
    turn = Turn()
    client = anthropic.AsyncAnthropic(max_retries=1, timeout=60)
    system = SYSTEM.format(name=CONTACT_NAME, resident=RESIDENT, pillow=PILLOW_ID, tz=TZ.key,
                           today=datetime.now(TZ).strftime("%A %Y-%m-%d"))
    messages = [*history, {"role": "user", "content": text}]
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": "calhacks-family-agent/1.0"}) as http:
        for _ in range(6):
            response = await client.beta.messages.create(
                model=MODEL, max_tokens=2048, betas=["server-side-fallback-2026-07-01"], fallbacks="default",
                system=system, tools=TOOLS, output_config={"effort": "low"}, messages=messages,
            )
            if response.stop_reason == "refusal":
                turn.text = "Sorry, I can't help with that one."
                return turn
            messages.append({"role": "assistant", "content": response.content})
            calls = [b for b in response.content if b.type == "tool_use"]
            if response.stop_reason != "tool_use" or not calls:
                turn.text = "".join(b.text for b in response.content if b.type == "text").strip()
                return turn
            results = []
            for call in calls:
                args = dict(call.input)
                try:
                    if call.name in WRITE_TOOLS:
                        turn.steps.append({"tool": call.name, "args": args})
                        label, value = describe(call.name, args)
                        out: Any = {"queued_for_approval": f"{label}: {value}"}
                    elif call.name == "show_goodnight_form":
                        turn.form = True
                        out = {"shown": True}
                    else:
                        out = await call_tool(http, storage, call.name, args)
                        if call.name == "get_night":
                            turn.night = out
                    results.append({"type": "tool_result", "tool_use_id": call.id,
                                    "content": json.dumps(out)})
                except Exception as err:  # noqa: BLE001 - tell Claude, it tells the family
                    results.append({"type": "tool_result", "tool_use_id": call.id, "is_error": True,
                                    "content": f"{type(err).__name__}: {err}"})
            messages.append({"role": "user", "content": results})
    turn.text = "Sorry, that took too many steps. Could you ask it another way?"
    return turn


def outcome(name: str, args: dict[str, Any], result: Any) -> str:
    """One carried-out step, in plain words, including what the Guardian changed or blocked."""
    label, value = describe(name, args)
    if isinstance(result, dict) and result.get("blocked"):
        return f"{label}: not done, the pillow's safety rules blocked it ({result['blocked']})"
    if name == "set_settings" and isinstance(result, dict) and result.get("guardian") == "blocked":
        return f"{label}: adjusted by the safety rules to {result.get('applied')} ({result.get('reason')})"
    return f"{label}: {value}"


async def run_plan(storage: Any, steps: list[dict[str, Any]]) -> str:
    lines = []
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": "calhacks-family-agent/1.0"}) as http:
        for step in steps:
            try:
                lines.append(outcome(step["tool"], step["args"],
                                     await call_tool(http, storage, step["tool"], step["args"])))
            except Exception as err:  # noqa: BLE001 - one failed step must not hide the others
                label, _ = describe(step["tool"], step["args"])
                lines.append(f"{label}: failed ({type(err).__name__}), please try that one again")
    return "Done. " + "; ".join(lines) + "."


def _text(msg: ChatMessage) -> str:
    return " ".join(c.text for c in msg.content if isinstance(c, TextContent)).strip()


def remember(storage: Any, sender: str, said: str, answered: str) -> None:
    """Keep the last few turns as plain text, including card clicks and what a plan did, so Claude
    knows on the next message what is already queued or done."""
    key = f"history:{sender}"
    turns = [*(storage.get(key) or []), {"role": "user", "content": said},
             {"role": "assistant", "content": answered}]
    storage.set(key, turns[-2 * HISTORY_TURNS:])


async def respond(ctx: Context, sender: str, text: str) -> ChatMessage:
    """Card clicks and yes/no to a pending plan are handled in plain code; the rest goes to Claude."""
    pending_key = f"plan:{sender}"
    pending = ctx.storage.get(pending_key)
    selection = cards.parse_selection(text)
    action = selection["action"] if selection else None
    if pending and action is None and pending["id"] in text:
        # ASI:One's planner relays a card click as prose that still carries the plan id
        action = cards.CANCEL_PLAN if re.search(r"cancel|reject", text, re.I) else cards.CONFIRM_PLAN
    done: str | None = None
    if pending and (action == cards.CONFIRM_PLAN or (action is None and YES.match(text))):
        if selection and selection.get("plan_id") != pending["id"]:
            return cards.reply("That plan has been replaced by a newer one; nothing changed.")
        ctx.storage.set(pending_key, None)
        said, done = "(confirmed the plan)", await run_plan(ctx.storage, pending["steps"])
    elif action == cards.CANCEL_PLAN or (pending and action is None and NO.match(text)):
        ctx.storage.set(pending_key, None)
        said, done = "(cancelled the plan)", "OK, nothing has changed."
    elif action == cards.GOODNIGHT_FORM:
        return cards.reply(f"What would you like {RESIDENT} to hear?", cards.goodnight_form(RESIDENT))
    elif action == cards.SEND_GOODNIGHT:
        args = {"message": str(selection.get("message") or "").strip(),
                "from_name": str(selection.get("from_name") or CONTACT_NAME).strip()}
        if not args["message"]:
            return cards.reply("The message was empty, so nothing was sent.")
        said = "(sent a goodnight from the form)"
        done = await run_plan(ctx.storage, [{"tool": "send_goodnight", "args": args}])
    elif action == cards.SHOW_LOG:
        text = "What exactly did the pillow and its agents do last night?"
    if done is not None:
        remember(ctx.storage, sender, said, done)
        return cards.reply(done)

    turn = await answer(ctx.storage, ctx.storage.get(f"history:{sender}") or [], text)
    reply_text = turn.text or "Done."
    if turn.steps:
        plan_id = uuid4().hex[:12]
        ctx.storage.set(pending_key, {"id": plan_id, "steps": turn.steps})
        rows = [describe(s["tool"], s["args"]) for s in turn.steps]
        queued = "; ".join(f"{label}: {value}" for label, value in rows)
        remember(ctx.storage, sender, text, f"{reply_text} [Plan shown for approval, not done yet: {queued}]")
        footer = " Reply yes to confirm or no to cancel."
        return cards.reply(reply_text + footer, cards.plan_review("Confirm the plan", rows, plan_id))
    remember(ctx.storage, sender, text, reply_text)
    if turn.form:
        return cards.reply(reply_text, cards.goodnight_form(RESIDENT))
    if turn.night is not None:
        return cards.reply(reply_text, cards.night_detail(turn.night["resident"], turn.night["summary"]))
    return cards.reply(reply_text)


@chat.on_message(ChatMessage)
async def on_chat(ctx: Context, sender: str, msg: ChatMessage) -> None:
    await ctx.send(sender, ChatAcknowledgement(timestamp=datetime.now(UTC), acknowledged_msg_id=msg.msg_id))
    text = _text(msg)
    if not text:
        return  # a start-session or attachment-only message: nothing to answer
    ctx.logger.info(f"{sender[:16]}...: {text}")
    try:
        message = await respond(ctx, sender, text)
    except Exception as err:  # noqa: BLE001
        ctx.logger.error(f"answer failed: {type(err).__name__}: {err}")
        message = cards.reply("Sorry, I couldn't reach the pillow just now. Please try again in a moment.")
    await ctx.send(sender, message)


@chat.on_message(ChatAcknowledgement)
async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement) -> None:
    ctx.logger.debug(f"ack from {sender[:16]} for {msg.acknowledged_msg_id}")


# ---------- the watch roster: answer the pillow's coordinator for this person ----------


@roster.on_message(AvailabilityRequest, replies=AvailabilityReply)
async def on_availability(ctx: Context, sender: str, msg: AvailabilityRequest) -> None:
    if sender != COORDINATOR or msg.pillow_id != PILLOW_ID:
        ctx.logger.warning(f"availability request from unknown {sender[:16]} ignored")
        return
    away = away_on(ctx.storage, msg.night)
    reason = f"{CONTACT_NAME} is away: {away['note']}" if away else f"{CONTACT_NAME} has no plans noted"
    ctx.logger.info(f"roster {msg.night}: {reason}")
    await ctx.send(sender, AvailabilityReply(contact_id=CONTACT_ID, available=away is None, reason=reason))


@agent.on_interval(period=600)
async def join_roster(ctx: Context) -> None:
    """Tell the coordinator who this agent speaks for (repeated, so a restarted coordinator relearns it)."""
    if COORDINATOR and CONTACT_ID:
        await ctx.send(COORDINATOR, JoinRoster(pillow_id=PILLOW_ID, contact_id=CONTACT_ID, name=CONTACT_NAME))


@agent.on_event("startup")
async def startup(ctx: Context) -> None:
    start_connect(ctx, PORT)


agent.include(chat, publish_manifest=True)
agent.include(roster, publish_manifest=True)

if __name__ == "__main__":
    for var, why in (("CHECKIN_TOKEN", "settings changes and the roster will fail"),
                     ("CONTACT_ID", "this agent can't take part in the evening roster"),
                     ("COORDINATOR_ADDRESS", "this agent can't take part in the evening roster")):
        if not os.environ.get(var):
            print(f"warning: {var} is not set, {why}", file=sys.stderr)
    print(f"family agent for {CONTACT_NAME}: {agent.address}")
    agent.run()
