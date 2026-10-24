# /// script
# requires-python = ">=3.12"
# dependencies = ["uagents>=0.25.5", "anthropic>=2.3", "httpx>=0.27"]
# ///
"""The family agent: the adult child talks to the pillow in ASI:One (coord/AGENT_FLOW.md section 7).

A uAgent on Agentverse (Agent Chat Protocol, mailbox) that speaks for one pillow. Everything the
adult child wants happens in the chat, no app needed:

    "How was Mum's night?"                     -> GET /night  (+ the Morning Brief if there is one)
    "Is she in bed now?"                       -> GET /state
    "Send Mum a goodnight message: ..."        -> POST /goodnight (played at her next lie-down)
    "Set quiet hours to 23:00-07:00"           -> PATCH /settings (the Guardian bounds it)
    "Give her 25 minutes before you check in"  -> PATCH /settings checkin_timeout_min

Claude reads the message and calls one of five tools; the tools only call the pillow backend, so
the agent can't do anything the API (and its Guardian) doesn't allow. Short per-sender history is
kept in agent storage so "and what about the night before?" works.

    export AGENT_SEED='<any long private phrase>'  ANTHROPIC_API_KEY=...  CHECKIN_TOKEN=<backend/.env>
    uv run agents/fetch/family_agent.py            # prints the agent address + Inspector link
Then on the Inspector: Connect -> Mailbox -> Finish. See agents/fetch/README.md.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    EndSessionContent,
    TextContent,
    chat_protocol_spec,
)

SERVER = os.environ.get("PILLOW_SERVER", "https://pillow.keanuc.net").rstrip("/")
PILLOW_ID = os.environ.get("PILLOW_ID", "mum")
TOKEN = os.environ.get("CHECKIN_TOKEN", "").strip()
MODEL = "claude-opus-5-5"
HISTORY_TURNS = 6
HERE = Path(__file__).resolve().parent

agent = Agent(
    name="pillow-family-agent",
    seed=os.environ.get("AGENT_SEED") or sys.exit("AGENT_SEED is not set"),
    port=int(os.environ.get("AGENT_PORT", "8001")),
    mailbox=True,
    publish_agent_details=True,
    readme_path=str(HERE / "README.md"),
)
chat = Protocol(spec=chat_protocol_spec)

SYSTEM = f"""\
You are the family agent of a bedside pillow that watches over an older person who lives alone \
(pillow id {PILLOW_ID}). You talk to her adult child in a chat. You have five tools that call the \
pillow's backend; use them for every factual question and every action, never answer from memory \
about the night. Keep replies short, warm and plain: 1-4 sentences, no bullet lists unless asked.
Rules: report only what the tools return; never guess why something happened; never name or hint \
at a medical condition; never give medical advice; never claim anyone called emergency services. \
If a settings change comes back clamped or blocked, say what was applied and why. For a goodnight \
message, send exactly the words they gave (ask if they didn't give any) and confirm it will play \
when she next lies down. If asked something the tools can't do, say so in one sentence."""

TOOLS: list[dict[str, Any]] = [
    {"name": "get_status", "description": "Live state now: is her head on the pillow, the night state "
     "(awake/in_bed/up/check_in/escalating), room light and temperature, when the pillow last reported.",
     "strict": True, "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "get_night", "description": "Last night: summary (lay down, asleep, trips with times and "
     "lengths, check-ins, alerts, who acknowledged, restless spells, anything unusual), the latest Morning "
     "Brief note if one exists, and current settings.", "strict": True,
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "send_goodnight", "description": "Queue a goodnight message in the sender's words; the pillow "
     "plays it when she next lies down.", "strict": True,
     "input_schema": {"type": "object", "properties": {
         "message": {"type": "string"}, "from_name": {"type": "string", "description": "who it's from"}},
         "required": ["message", "from_name"], "additionalProperties": False}},
    {"name": "set_settings", "description": "Change quiet hours (HH:MM) and/or the minutes before the pillow "
     "checks in after she gets up (10-30). Only pass the keys being changed.", "strict": True,
     "input_schema": {"type": "object", "properties": {
         "quiet_start": {"type": ["string", "null"]}, "quiet_end": {"type": ["string", "null"]},
         "checkin_timeout_min": {"type": ["integer", "null"]}},
         "required": ["quiet_start", "quiet_end", "checkin_timeout_min"], "additionalProperties": False}},
    {"name": "get_agent_log", "description": "What the pillow's agents did last night, step by step, with "
     "the Guardian's allowed/blocked verdicts. For 'what exactly did it do' questions.", "strict": True,
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
]


async def call_tool(http: httpx.AsyncClient, name: str, args: dict[str, Any]) -> Any:
    base = f"{SERVER}/api/pillows/{PILLOW_ID}"
    auth = {"Authorization": f"Bearer {TOKEN}"}
    if name == "get_status":
        r = await http.get(f"{base}/state")
        r.raise_for_status()
        s = r.json()
        return {k: s[k] for k in ("night_state", "head_on", "light", "temp_c", "humidity", "last_seen_at",
                                  "state_since")}
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
    return {"error": f"unknown tool {name}"}


async def answer(history: list[dict[str, Any]], text: str) -> str:
    """One Claude tool loop over the backend; returns the reply text."""
    import anthropic

    client = anthropic.AsyncAnthropic(max_retries=1, timeout=30)
    messages = [*history, {"role": "user", "content": text}]
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": "calhacks-family-agent/1.0"}) as http:
        for _ in range(5):
            response = await client.beta.messages.create(
                model=MODEL, max_tokens=2048, betas=["server-side-fallback-2026-07-01"], fallbacks="default",
                system=SYSTEM, tools=TOOLS, output_config={"effort": "low"}, messages=messages,
            )
            if response.stop_reason == "refusal":
                return "Sorry, I can't help with that one."
            messages.append({"role": "assistant", "content": response.content})
            calls = [b for b in response.content if b.type == "tool_use"]
            if response.stop_reason != "tool_use" or not calls:
                return "".join(b.text for b in response.content if b.type == "text").strip() or "Done."
            results = []
            for call in calls:
                try:
                    out = await call_tool(http, call.name, dict(call.input))
                    results.append({"type": "tool_result", "tool_use_id": call.id,
                                    "content": json.dumps(out)})
                except Exception as err:  # noqa: BLE001 - tell Claude, it tells the family
                    results.append({"type": "tool_result", "tool_use_id": call.id, "is_error": True,
                                    "content": f"{type(err).__name__}: {err}"})
            messages.append({"role": "user", "content": results})
    return "Sorry, that took too many steps. Could you ask it another way?"


def _text(msg: ChatMessage) -> str:
    return " ".join(c.text for c in msg.content if isinstance(c, TextContent)).strip()


@chat.on_message(ChatMessage)
async def on_chat(ctx: Context, sender: str, msg: ChatMessage) -> None:
    await ctx.send(sender, ChatAcknowledgement(timestamp=datetime.now(UTC), acknowledged_msg_id=msg.msg_id))
    text = _text(msg)
    if not text:
        return  # a start-session or attachment-only message: nothing to answer
    key = f"history:{sender}"
    history = ctx.storage.get(key) or []
    ctx.logger.info(f"{sender[:16]}...: {text}")
    try:
        reply = await answer(history, text)
    except Exception as err:  # noqa: BLE001
        ctx.logger.error(f"answer failed: {type(err).__name__}: {err}")
        reply = "Sorry, I couldn't reach the pillow just now. Please try again in a moment."
    # keep only plain text turns in history (tool blocks don't serialise into storage)
    history = [*history, {"role": "user", "content": text}, {"role": "assistant", "content": reply}]
    ctx.storage.set(key, history[-2 * HISTORY_TURNS:])
    await ctx.send(sender, ChatMessage(timestamp=datetime.now(UTC), msg_id=uuid4(),
                                       content=[TextContent(type="text", text=reply),
                                                EndSessionContent(type="end-session")]))


@chat.on_message(ChatAcknowledgement)
async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement) -> None:
    ctx.logger.debug(f"ack from {sender[:16]} for {msg.acknowledged_msg_id}")


agent.include(chat, publish_manifest=True)

if __name__ == "__main__":
    if not TOKEN:
        print("warning: CHECKIN_TOKEN is not set, settings changes will fail", file=sys.stderr)
    print(f"family agent address: {agent.address}")
    agent.run()
