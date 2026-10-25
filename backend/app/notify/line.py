"""Live alert calls on Cartesia Line: a Claude agent rings the contact, says the alert in the
pillow's voice, answers what they ask (it can read the pillow's live state) and, if they say they
are on their way, tells the pillow, which stops alerting the others.

The agent itself (prompt, tools, model) is set up by scripts/setup_line.py. Cartesia sets the voice
per agent, so a call in another voice uses a copy of that agent, made here the first time it's
needed. The call speaks in the voice she hears at night, except that nobody is called in a clone
of their own voice: then it is the pillow's default voice.
"""

import asyncio
import logging
from typing import Any

import httpx
from supabase import AsyncClient

from app.core.config import Settings
from app.core.voice_constants import CARTESIA_API, CARTESIA_VERSION, DEFAULT_VOICE_ID, VOICE_IDS
from app.crud.pillows import get_pillow
from app.crud.residents import get_resident
from app.crud.voice_clones import get_voice_clone
from app.notify.notify_constants import (
    HTTP_TIMEOUT_S,
    LINE_AGENT_NAME,
    LINE_AGENTS_PATH,
    LINE_API_PATH,
    LINE_DONE,
    LINE_MISSED,
    LINE_NEW_AGENT_TRIES,
    LINE_NEW_AGENT_WAIT_S,
    LINE_RING_S,
    LINE_VOICEMAIL_TOOL,
)
from app.notify.transports import DeliveryError, _reason

log = logging.getLogger(__name__)


async def call_voice(db: AsyncClient, pillow_id: str, contact_id: str | None) -> str:
    """The voice to call `contact_id` in: the pillow's current voice, unless it is a clone that
    contact made (directly or as the base of an accent copy), or anything goes wrong."""
    try:
        pillow = await get_pillow(db, pillow_id)
        resident = await get_resident(db, str(pillow.resident_id)) if pillow and pillow.resident_id else None
        voice = (resident or {}).get("voice_id") or DEFAULT_VOICE_ID
        if voice in VOICE_IDS:
            return voice
        clone = await get_voice_clone(db, resident["id"], voice)
        makers = {clone and clone.get("created_by")}
        if clone and clone.get("base_voice_id"):
            base = await get_voice_clone(db, resident["id"], clone["base_voice_id"])
            makers.add(base and base.get("created_by"))
        return voice if clone and str(contact_id) not in {str(m) for m in makers if m} else DEFAULT_VOICE_ID
    except Exception as err:  # the call matters more than the voice
        log.warning("Call voice lookup failed (%s); using the default voice", type(err).__name__)
        return DEFAULT_VOICE_ID


def _with_voice(config: dict[str, Any], voice_id: str) -> dict[str, Any]:
    """The base agent's config speaking in `voice_id` (minus what Cartesia derives itself).
    scripts/setup_line.py does the same for the copies it updates."""
    audio = config.get("audio") or {}
    output = {**(audio.get("output") or {}), "voice_id": voice_id}
    copy = {k: v for k, v in config.items() if k != "dynamic_variable_placeholders"}
    return {**copy, "audio": {**audio, "output": output}}


class CartesiaLine:
    """Cartesia's agents API: place an agent's outbound call and read how it went."""

    def __init__(self, api_key: str, agent_id: str, number_id: str, db: AsyncClient | None,
                 http: httpx.AsyncClient | None = None) -> None:
        self.agent_id, self.number_id, self.db = agent_id, number_id, db
        self.http = http or httpx.AsyncClient(
            base_url=CARTESIA_API, timeout=HTTP_TIMEOUT_S,
            headers={"Authorization": f"Bearer {api_key}", "Cartesia-Version": CARTESIA_VERSION})
        self._agents: dict[str, str] = {}  # voice id -> its agent's id
        self._lock = asyncio.Lock()

    @classmethod
    def from_settings(cls, settings: Settings, db: AsyncClient | None) -> "CartesiaLine | None":
        key, agent, number = (settings.cartesia_api_key, settings.cartesia_line_agent_id,
                              settings.cartesia_line_number_id)
        return cls(key, agent, number, db) if key and agent and number else None

    async def call(self, row: dict[str, Any], phone: str) -> str:
        """Ring `phone` for notification `row`; the call's id. Raises DeliveryError."""
        incident = row.get("incidents") or {}
        contact = row.get("contacts") or {}
        voice = DEFAULT_VOICE_ID
        if self.db is not None:
            voice = await call_voice(self.db, incident.get("pillow_id"), row.get("contact_id"))
        variables = {
            "contact_name": (contact.get("full_name") or "there").split()[0],
            "alert": row.get("message") or incident.get("summary") or "",
            "summary": incident.get("summary") or "",
            "pillow_id": incident.get("pillow_id") or "",
            "contact_id": str(row.get("contact_id") or ""),
        }
        body = {"agent_id": await self.agent_for(voice), "from_number_id": self.number_id,
                "ringing_timeout_seconds": LINE_RING_S,
                "outbound_calls": [{"to_number": phone, "dynamic_variables": variables}]}
        placed = (await self._place(body)).get("calls") or [{}]
        if not placed[0].get("agent_call_id"):
            raise DeliveryError(f"Line refused the call: {str(placed[0].get('error') or placed)[:200]}")
        return placed[0]["agent_call_id"]

    async def missed(self, call_id: str) -> tuple[bool, str | None]:
        """(whether the call is over, why it didn't reach a person or None if it did)."""
        call = await self._send("GET", f"{LINE_API_PATH}/{call_id}")
        if call.get("status") not in LINE_DONE:
            return False, None
        if call.get("end_reason") in LINE_MISSED:
            return True, LINE_MISSED[call["end_reason"]]
        if call.get("status") == "failed":
            return True, "couldn't be called"
        turns = call.get("transcript") or []
        tools = {tool.get("name") for turn in turns for tool in turn.get("tool_calls") or []}
        heard = any(turn.get("role") == "user" and (turn.get("text") or "").strip() for turn in turns)
        if LINE_VOICEMAIL_TOOL in tools or not heard:
            return True, "didn't pick up (voicemail)"
        return True, None

    async def agent_for(self, voice_id: str) -> str:
        """The agent that speaks in `voice_id`: the base agent's copy, made once if need be."""
        async with self._lock:
            if voice_id in self._agents:
                return self._agents[voice_id]
            base = await self._send("GET", f"{LINE_AGENTS_PATH}/{self.agent_id}")
            if base["config"]["audio"]["output"]["voice_id"] == voice_id:
                self._agents[voice_id] = self.agent_id
                return self.agent_id
            name = f"{LINE_AGENT_NAME} ({voice_id})"
            listed = (await self._send("GET", LINE_AGENTS_PATH)).get("data") or []
            found = next((agent["id"] for agent in listed if agent.get("name") == name), None)
            if found is None:  # setup_line.py keeps existing copies in step with the base agent
                found = (await self._send("POST", LINE_AGENTS_PATH, json={
                    "name": name, "description": base.get("description"),
                    "config": _with_voice(base["config"], voice_id)}))["id"]
                log.info("Made a Line agent for voice %s", voice_id)
            self._agents[voice_id] = found
            return found

    async def _place(self, body: dict[str, Any]) -> dict[str, Any]:
        """POST the call; a just-made (or just-changed) agent answers 404 for a few seconds."""
        for attempt in range(LINE_NEW_AGENT_TRIES):
            try:
                return await self._send("POST", LINE_API_PATH, json=body)
            except DeliveryError as err:
                if "404" not in str(err) or attempt == LINE_NEW_AGENT_TRIES - 1:
                    raise
                await asyncio.sleep(LINE_NEW_AGENT_WAIT_S)
        raise AssertionError("unreachable")

    async def _send(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = await self.http.request(method, path, **kwargs)
        except httpx.HTTPError as err:
            raise DeliveryError(f"Line unreachable ({type(err).__name__})") from err
        if response.status_code >= 300:
            raise DeliveryError(f"Line {_reason(response)}")
        return response.json()
