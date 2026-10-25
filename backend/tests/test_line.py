"""Live alert calls on Cartesia Line, offline: the sender tries Line first and falls back to Twilio,
how a finished call is read, the per-voice agents, and which voice a contact is called in."""

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from app.core.voice_constants import DEFAULT_VOICE_ID
from app.notify import line as line_module
from app.notify import sender as sender_module
from app.notify.line import CartesiaLine, call_voice
from app.notify.sender import NotificationSender
from app.notify.transports import DeliveryError
from tests.test_notify import PHONE, FakeIMessage, FakeTwilio, row

CLONE = "clone-of-sarah"


def call_row(**kw):
    return {**row("call", **kw), "contact_id": "c-sarah"}


class FakeLine:
    def __init__(self, fail=None, outcome=((True, None),)):
        self.fail, self.calls, self.outcome = fail, [], list(outcome)

    async def call(self, r, phone):
        if self.fail:
            raise DeliveryError(self.fail)
        self.calls.append((r["contact_id"], phone))
        return "ac_1"

    async def missed(self, call_id):
        return self.outcome.pop(0) if len(self.outcome) > 1 else self.outcome[0]


# ---------- the sender ----------

def test_call_goes_by_line_first():
    tw, ln = FakeTwilio(), FakeLine()
    result = asyncio.run(NotificationSender(FakeIMessage(), tw, ["mum"], line=ln).deliver(call_row()))
    assert (result.sent, result.via, result.ref, result.error) == (True, "call", "line:ac_1", None)
    assert ln.calls == [("c-sarah", PHONE)] and tw.calls == []


def test_line_failure_falls_back_to_twilio_and_says_why():
    tw = FakeTwilio()
    sender = NotificationSender(FakeIMessage(), tw, ["mum"], line=FakeLine("Line 402: out of credits"))
    result = asyncio.run(sender.deliver(call_row()))
    assert (result.sent, result.ref) == (True, "CA1") and "out of credits" in result.error
    assert tw.calls == [(PHONE, "Margaret hasn't come back to bed.", None)]


def test_line_failure_without_twilio_fails_with_lines_reason():
    sender = NotificationSender(None, None, ["mum"], line=FakeLine("Line down"))
    result = asyncio.run(sender.deliver(call_row()))
    assert (result.sent, result.error) == (False, "Line down")


def follow_line(monkeypatch, ln, r):
    logged = []

    async def fake_log(db, pillow_id, agent, intent, **kw):
        logged.append(intent)

    monkeypatch.setattr(sender_module, "log_action", fake_log)
    monkeypatch.setattr(sender_module, "CALL_POLL_S", 0)
    tw = FakeTwilio()
    sender = NotificationSender(FakeIMessage("down"), tw, ["mum"], line=ln)
    asyncio.run(sender.follow_call(None, r, "line:ac_1"))
    return logged, tw


def test_line_voicemail_is_followed_by_a_text(monkeypatch):
    ln = FakeLine(outcome=[(False, None), (True, "didn't pick up (voicemail)")])
    logged, tw = follow_line(monkeypatch, ln, call_row())
    assert tw.texts == [(PHONE, "Margaret hasn't come back to bed.")]
    assert logged == ["Sarah didn't pick up (voicemail), so texted them (SMS)"]


def test_line_conversation_sends_nothing_more(monkeypatch):
    logged, tw = follow_line(monkeypatch, FakeLine(outcome=[(False, None), (True, None)]), call_row())
    assert logged == [] and tw.texts == []


# ---------- the HTTP client ----------

BASE = {"id": "agent_base", "description": "Calls family",
        "config": {"instructions": "hi", "dynamic_variable_placeholders": ["x"],
                   "audio": {"input": {}, "output": {"voice_id": DEFAULT_VOICE_ID, "speed": 0.95}}}}


def client(handler, db=None):
    http = httpx.AsyncClient(base_url="https://line.test", transport=httpx.MockTransport(handler))
    return CartesiaLine("key", "agent_base", "ap_1", db, http=http)


def test_call_posts_the_alert_as_dynamic_variables():
    seen = []

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json=BASE)
        seen.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={"calls": [{"agent_call_id": "ac_9"}]})

    assert asyncio.run(client(handler).call(call_row(), PHONE)) == "ac_9"
    path, body = seen[0]
    assert path == "/agents/calls" and body["agent_id"] == "agent_base" and body["from_number_id"] == "ap_1"
    assert body["outbound_calls"] == [{"to_number": PHONE, "dynamic_variables": {
        "contact_name": "Sarah", "alert": "Margaret hasn't come back to bed.", "summary": "Out of bed 20 min",
        "pillow_id": "mum", "contact_id": "c-sarah"}}]


def test_a_just_made_agent_is_retried_until_callable(monkeypatch):
    monkeypatch.setattr(line_module, "LINE_NEW_AGENT_WAIT_S", 0)
    answers = [httpx.Response(404, json={"message": "The requested agent does not exist."})] * 2

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json=BASE)
        return answers.pop(0) if answers else httpx.Response(200, json={"calls": [{"agent_call_id": "ac_2"}]})

    assert asyncio.run(client(handler).call(call_row(), PHONE)) == "ac_2"


def test_a_refused_call_entry_is_a_delivery_error():
    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json=BASE)
        return httpx.Response(200, json={"calls": [{"error": "invalid number"}]})

    with pytest.raises(DeliveryError, match="invalid number"):
        asyncio.run(client(handler).call(call_row(), PHONE))


def test_an_http_error_is_a_delivery_error():
    with pytest.raises(DeliveryError, match="Line 401"):
        asyncio.run(client(lambda r: httpx.Response(401, json={"message": "bad key"})).missed("ac_1"))


@pytest.mark.parametrize(("call", "expected"), [
    ({"status": "started"}, (False, None)),
    ({"status": "completed", "end_reason": "dial_no_answer"}, (True, "didn't answer")),
    ({"status": "completed", "end_reason": "dial_busy"}, (True, "rejected the call")),
    ({"status": "failed", "end_reason": None}, (True, "couldn't be called")),
    ({"status": "completed", "end_reason": "agent_hangup", "transcript": [
        {"role": "assistant", "text": "Hi", "tool_calls": [{"name": "left_voicemail"}]},
        {"role": "user", "text": "Leave a message after the tone"}]}, (True, "didn't pick up (voicemail)")),
    ({"status": "completed", "end_reason": "inactivity", "transcript": [{"role": "user", "text": " "}]},
     (True, "didn't pick up (voicemail)")),
    ({"status": "completed", "end_reason": "agent_hangup", "transcript": [
        {"role": "user", "text": "Hello?"}, {"role": "assistant", "text": "Hi Sarah"}]}, (True, None)),
])
def test_how_a_finished_call_is_read(call, expected):
    assert asyncio.run(client(lambda r: httpx.Response(200, json=call)).missed("ac_1")) == expected


def test_other_voices_get_a_copy_of_the_agent_made_once():
    seen, agents = [], []

    def handler(request):
        seen.append((request.method, request.url.path))
        if request.url.path == "/v1/agents/agent_base":
            return httpx.Response(200, json=BASE)
        if request.method == "GET":
            return httpx.Response(200, json={"data": agents})
        body = json.loads(request.content)
        assert body["config"]["audio"]["output"] == {"voice_id": CLONE, "speed": 0.95}
        assert "dynamic_variable_placeholders" not in body["config"]
        if request.method == "POST":
            agents.append({"id": "agent_copy", "name": body["name"]})
        return httpx.Response(200, json={"id": "agent_copy"})

    line = client(handler)
    assert asyncio.run(line.agent_for(DEFAULT_VOICE_ID)) == "agent_base"
    assert asyncio.run(line.agent_for(CLONE)) == "agent_copy"
    assert asyncio.run(line.agent_for(CLONE)) == "agent_copy"  # cached: no more requests
    assert [m for m, _ in seen].count("POST") == 1
    later = client(handler)  # a restarted backend finds the copy
    assert asyncio.run(later.agent_for(CLONE)) == "agent_copy"
    assert [m for m, _ in seen].count("POST") == 1 and "PATCH" not in [m for m, _ in seen]
    assert BASE["config"]["audio"]["output"]["voice_id"] == DEFAULT_VOICE_ID  # base left alone


# ---------- which voice ----------

def voices(monkeypatch, current, clones):
    async def get_pillow(db, pillow_id):
        return SimpleNamespace(resident_id="r1")

    async def get_resident(db, resident_id):
        return {"id": "r1", "voice_id": current}

    async def get_voice_clone(db, resident_id, voice_id):
        return clones.get(voice_id)

    monkeypatch.setattr(line_module, "get_pillow", get_pillow)
    monkeypatch.setattr(line_module, "get_resident", get_resident)
    monkeypatch.setattr(line_module, "get_voice_clone", get_voice_clone)
    return lambda contact: asyncio.run(call_voice(object(), "mum", contact))


def test_calls_use_the_pillows_current_voice(monkeypatch):
    voice = voices(monkeypatch, CLONE, {CLONE: {"voice_id": CLONE, "created_by": "c-sarah"}})
    assert voice("c-tom") == CLONE


def test_nobody_is_called_in_their_own_voice(monkeypatch):
    voice = voices(monkeypatch, CLONE, {CLONE: {"voice_id": CLONE, "created_by": "c-sarah"}})
    assert voice("c-sarah") == DEFAULT_VOICE_ID


def test_nor_in_an_accent_copy_of_it(monkeypatch):
    clones = {CLONE: {"voice_id": CLONE, "created_by": "c-sarah"},
              "accent": {"voice_id": "accent", "created_by": "c-tom", "base_voice_id": CLONE}}
    voice = voices(monkeypatch, "accent", clones)
    assert [voice(c) for c in ("c-sarah", "c-tom", "c-ann")] == [DEFAULT_VOICE_ID, DEFAULT_VOICE_ID, "accent"]


def test_unknown_voice_or_lookup_failure_uses_the_default(monkeypatch):
    assert voices(monkeypatch, "not-hers", {})("c-sarah") == DEFAULT_VOICE_ID

    async def broken(db, pillow_id):
        raise RuntimeError("db down")

    monkeypatch.setattr(line_module, "get_pillow", broken)
    assert asyncio.run(call_voice(object(), "mum", "c-sarah")) == DEFAULT_VOICE_ID
