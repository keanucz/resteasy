# /// script
# requires-python = ">=3.12"
# dependencies = ["uagents==0.25.5", "uagents-core==0.4.9", "httpx>=0.27"]
# ///
"""The pillow's coordinator: each evening it asks every family member's agent, all at once, "can your
person be called first tonight?", and sets tonight's on-call roster from the answers.

A uAgent on Agentverse (mailbox). Family agents (family_agent.py) join it by sending JoinRoster; it
keeps only those whose contact really looks after this pillow's resident (GET /roster, the household
allow-list). At ROSTER_AT in her timezone, or when someone asks it in ASI:One:

    1. AvailabilityRequest to every member in parallel, answers awaited for ROSTER_TIMEOUT_S
    2. available -> on call, away -> off call, through PUT /roster/{contact_id} (Guardian-checked:
       the last on-call contact never goes off), people going on call first
    3. no answer -> that person is left exactly as they were

Safe by construction: Night Watch only reads `on_call` to choose who it tries FIRST and still alerts
every contact in the end, so a wrong, late or missing roster can reorder help but never withhold it.
If this agent is down, last night's roster simply stays. Plain code throughout, no LLM.

    export AGENT_SEED='<private phrase>'  AGENT_TOKEN=<the backend's COORDINATOR_TOKEN>  PILLOW_ID=mum
    uv run agents/fetch/coordinator_agent.py
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

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
# The backend's COORDINATOR_TOKEN; CHECKIN_TOKEN until the backend has one
TOKEN = (os.environ.get("AGENT_TOKEN") or os.environ.get("CHECKIN_TOKEN", "")).strip()
ROSTER_AT = os.environ.get("ROSTER_AT", "21:00")  # HH:MM in her timezone
ROSTER_TIMEOUT_S = int(os.environ.get("ROSTER_TIMEOUT_S", "30"))
HERE = Path(__file__).resolve().parent
PORT = int(os.environ.get("AGENT_PORT", "8010"))
RUN_NOW = re.compile(r"\b(plan|roster|run|ask|tonight|who.{0,20}call)\b", re.I)

agent = Agent(
    name=os.environ.get("AGENT_NAME") or f"pillow-coordinator-{PILLOW_ID}",
    seed=os.environ.get("AGENT_SEED") or sys.exit("AGENT_SEED is not set"),
    port=PORT,
    # Agentverse mailbox in production; AGENT_ENDPOINT (http://127.0.0.1:<port>/submit) for local tests
    mailbox=not os.environ.get("AGENT_ENDPOINT"),
    endpoint=[os.environ["AGENT_ENDPOINT"]] if os.environ.get("AGENT_ENDPOINT") else None,
    publish_agent_details=True,
    readme_path=str(HERE / "README.md"),
    description="The bedside pillow's coordinator: each evening it asks every family member's agent who "
    "can be called first tonight and sets the on-call roster. Ask it what's happening with the pillow.",
)
chat = Protocol(spec=chat_protocol_spec)
roster = roster_protocol()


def _http() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=20, headers={"User-Agent": "calhacks-coordinator/1.0",
                                                  "Authorization": f"Bearer {TOKEN}"})


async def household(http: httpx.AsyncClient) -> dict[str, Any]:
    """GET /roster: the resident, her timezone and her contacts in alert order."""
    r = await http.get(f"{SERVER}/api/pillows/{PILLOW_ID}/roster")
    r.raise_for_status()
    return r.json()


async def ask(ctx: Context, address: str, night: str) -> AvailabilityReply | None:
    reply, status = await ctx.send_and_receive(
        address, AvailabilityRequest(pillow_id=PILLOW_ID, night=night), response_type=AvailabilityReply,
        timeout=ROSTER_TIMEOUT_S,
    )
    if not isinstance(reply, AvailabilityReply):
        ctx.logger.warning(f"no answer from {address[:16]}: {status.detail}")
        return None
    return reply


async def run_roster(ctx: Context) -> str:
    """One round: ask every member at once, then set on-call flags. Returns a summary line per person."""
    async with _http() as http:
        house = await household(http)
        night = datetime.now(ZoneInfo(house["timezone"])).date().isoformat()
        contacts = {c["contact_id"]: c for c in house["contacts"]}
        members = {cid: m for cid, m in (ctx.storage.get("members") or {}).items() if cid in contacts}
        replies = await asyncio.gather(*(ask(ctx, m["address"], night) for m in members.values()),
                                       return_exceptions=True)
        answers: dict[str, AvailabilityReply] = {}
        lines: list[str] = []
        for cid, rep in zip(members, replies, strict=True):
            if isinstance(rep, AvailabilityReply) and rep.contact_id == cid:
                answers[cid] = rep
            else:
                lines.append(f"{contacts[cid]['name']}: their agent didn't answer, left as before")
        # Put people on call before taking anyone off, so the Guardian's "someone stays on call" rule
        # judges the final roster, not a half-applied one.
        for cid, rep in sorted(answers.items(), key=lambda kv: not kv[1].available):
            want = rep.available
            if contacts[cid]["on_call"] == want:
                lines.append(f"{contacts[cid]['name']}: {'on' if want else 'off'} call ({rep.reason})")
                continue
            r = await http.put(f"{SERVER}/api/pillows/{PILLOW_ID}/roster/{cid}",
                               json={"on_call": want, "reason": rep.reason[:200]})
            r.raise_for_status()
            result = r.json()
            if result["guardian"] == "blocked":
                lines.append(f"{contacts[cid]['name']}: stays on call, {result['reason']} ({rep.reason})")
            else:
                lines.append(f"{contacts[cid]['name']}: {'on' if want else 'off'} call ({rep.reason})")
        for cid, c in contacts.items():
            if cid not in members:
                lines.append(f"{c['name']}: no agent yet, left {'on' if c['on_call'] else 'off'} call")
    summary = f"Tonight's watch for {house['resident']} ({night}): " + "; ".join(lines) + "."
    ctx.storage.set("last_roster", {"night": night, "summary": summary})
    ctx.logger.info(summary)
    return summary


@roster.on_message(JoinRoster)
async def on_join(ctx: Context, sender: str, msg: JoinRoster) -> None:
    """A family agent speaks for a contact; keep it only if that contact looks after this resident."""
    if msg.pillow_id != PILLOW_ID:
        return
    try:
        async with _http() as http:
            known = {c["contact_id"] for c in (await household(http))["contacts"]}
    except httpx.HTTPError as err:
        ctx.logger.error(f"roster unavailable, join from {sender[:16]} not checked: {err}")
        return
    if msg.contact_id not in known:
        ctx.logger.warning(f"{sender[:16]} claims contact {msg.contact_id}, not in the household; ignored")
        return
    members = ctx.storage.get("members") or {}
    if members.get(msg.contact_id, {}).get("address") != sender:
        ctx.logger.info(f"{msg.name}'s agent joined the roster: {sender}")
    members[msg.contact_id] = {"address": sender, "name": msg.name}
    ctx.storage.set("members", members)


@agent.on_interval(period=60)
async def evening(ctx: Context) -> None:
    """Run the roster once a night, at ROSTER_AT in her timezone (or as soon after as we're up)."""
    try:
        async with _http() as http:
            tz = ZoneInfo((await household(http))["timezone"])
    except httpx.HTTPError as err:
        ctx.logger.error(f"backend unreachable: {err}")
        return
    now = datetime.now(tz)
    if now.strftime("%H:%M") < ROSTER_AT or ctx.storage.get("last_auto_night") == now.date().isoformat():
        return
    ctx.storage.set("last_auto_night", now.date().isoformat())
    try:
        await run_roster(ctx)
    except Exception as err:  # noqa: BLE001 - tomorrow's run tries again; tonight keeps last roster
        ctx.logger.error(f"roster failed: {type(err).__name__}: {err}")


async def status_text(ctx: Context) -> str:
    async with httpx.AsyncClient(timeout=20) as http:
        r = await http.get(f"{SERVER}/api/pillows/{PILLOW_ID}/state")
        state = r.json() if r.status_code == 200 else {}
    members = ctx.storage.get("members") or {}
    last = ctx.storage.get("last_roster")
    night_state = state.get("night_state") or "unknown"
    bed = "in bed" if state.get("head_on") else "not in bed"
    who = ", ".join(m["name"] for m in members.values()) or "no family agents yet"
    parts = [f"The pillow says she is {bed}; night state: {night_state}.",
             f"Family agents on the roster: {who}.",
             last["summary"] if last else "No roster has run yet.",
             f"Say \"plan tonight\" to ask everyone now (it also runs by itself at {ROSTER_AT})."]
    return " ".join(parts)


@chat.on_message(ChatMessage)
async def on_chat(ctx: Context, sender: str, msg: ChatMessage) -> None:
    await ctx.send(sender, ChatAcknowledgement(timestamp=datetime.now(UTC), acknowledged_msg_id=msg.msg_id))
    text = " ".join(c.text for c in msg.content if isinstance(c, TextContent)).strip()
    if not text:
        return
    ctx.logger.info(f"{sender[:16]}...: {text}")
    try:
        reply = await run_roster(ctx) if RUN_NOW.search(text) else await status_text(ctx)
    except Exception as err:  # noqa: BLE001
        ctx.logger.error(f"chat failed: {type(err).__name__}: {err}")
        reply = "Sorry, I couldn't reach the pillow just now. Please try again in a moment."
    await ctx.send(sender, cards.reply(reply))


@chat.on_message(ChatAcknowledgement)
async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement) -> None:
    ctx.logger.debug(f"ack from {sender[:16]} for {msg.acknowledged_msg_id}")


@agent.on_event("startup")
async def startup(ctx: Context) -> None:
    start_connect(ctx, PORT)


agent.include(chat, publish_manifest=True)
agent.include(roster, publish_manifest=True)

if __name__ == "__main__":
    if not TOKEN:
        sys.exit("AGENT_TOKEN (or CHECKIN_TOKEN) is not set: the coordinator can't read or set the roster")
    print(f"coordinator for {PILLOW_ID}: {agent.address}")
    agent.run()
