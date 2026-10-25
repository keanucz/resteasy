"""The notifications sender, offline: which provider each row goes to, and what the row records."""

import asyncio
from urllib.parse import parse_qs

import httpx
import pytest

from app.notify import sender as sender_module
from app.notify.sender import NotificationSender
from app.notify.transports import DeliveryError, IMessage, Twilio

PHONE = "+15551234567"


def row(channel="sms", consent=True, phone=PHONE, message="Margaret hasn't come back to bed."):
    return {"id": 7, "incident_id": 3, "channel": channel, "message": message,
            "contacts": {"full_name": "Sarah Lee", "phone": phone, "sms_consent": consent},
            "incidents": {"pillow_id": "mum", "summary": "Out of bed 20 min"}}


class FakeIMessage:
    def __init__(self, fail: str | None = None):
        self.fail, self.sent = fail, []

    async def send(self, to, text):
        if self.fail:
            raise DeliveryError(self.fail)
        self.sent.append((to, text))
        return "guid-1"


class FakeTwilio:
    def __init__(self, fail: str | None = None, outcome=(("completed", "human"),)):
        self.fail, self.texts, self.calls = fail, [], []
        self.outcome = list(outcome)  # what call_status answers, one per check; the last repeats

    async def sms(self, to, body):
        if self.fail:
            raise DeliveryError(self.fail)
        self.texts.append((to, body))
        return "SM1"

    async def call(self, to, say):
        if self.fail:
            raise DeliveryError(self.fail)
        self.calls.append((to, say))
        return "CA1"

    async def call_status(self, sid):
        return self.outcome.pop(0) if len(self.outcome) > 1 else self.outcome[0]


def deliver(sender, r):
    return asyncio.run(sender.deliver(r))


# ---------- routing ----------

def test_text_goes_by_imessage_first():
    im, tw = FakeIMessage(), FakeTwilio()
    result = deliver(NotificationSender(im, tw, ["mum"]), row())
    assert (result.sent, result.via, result.ref) == (True, "imessage", "imessage:guid-1")
    assert im.sent == [(PHONE, "Margaret hasn't come back to bed.")] and tw.texts == []


def test_text_falls_back_to_sms_and_says_why():
    tw = FakeTwilio()
    result = deliver(NotificationSender(FakeIMessage("502: Target not allowed"), tw, ["mum"]), row())
    assert (result.sent, result.via, result.ref) == (True, "sms", "SM1")
    assert "Target not allowed" in result.error
    assert tw.texts == [(PHONE, "Margaret hasn't come back to bed.")]


def test_text_fails_when_both_fail():
    result = deliver(NotificationSender(FakeIMessage("down"), FakeTwilio("bad number"), ["mum"]), row())
    assert not result.sent and "iMessage down" in result.error and "SMS bad number" in result.error


def test_call_goes_by_twilio_and_needs_no_text_consent():
    tw = FakeTwilio()
    result = deliver(NotificationSender(FakeIMessage(), tw, ["mum"]), row("call", consent=False))
    assert (result.sent, result.ref) == (True, "CA1") and tw.calls


def test_call_without_twilio_fails():
    assert not deliver(NotificationSender(FakeIMessage(), None, ["mum"]), row("call")).sent


# ---------- refusals ----------

def test_no_text_without_consent():
    im, tw = FakeIMessage(), FakeTwilio()
    result = deliver(NotificationSender(im, tw, ["mum"]), row(consent=False))
    assert not result.sent and "sms_consent" in result.error and not im.sent and not tw.texts


def test_no_phone_no_send():
    assert deliver(NotificationSender(FakeIMessage(), FakeTwilio(), ["mum"]), row(phone=None)).error == \
        "no phone number on record"


def test_older_rows_fall_back_to_the_incident_summary():
    im = FakeIMessage()
    deliver(NotificationSender(im, None, ["mum"]), row(message=None))
    assert im.sent == [(PHONE, "Out of bed 20 min")]


def test_disabled_without_providers_or_pillows():
    assert not NotificationSender(None, None, ["mum"]).enabled
    assert not NotificationSender(FakeIMessage(), None, []).enabled
    assert NotificationSender(None, FakeTwilio(), ["mum"]).enabled


# ---------- tick ----------

def test_tick_records_each_row_and_logs_it(monkeypatch):
    finished, logged, asked = [], [], {}

    async def fake_list(db, channels, pillow_ids, since):
        asked.update(channels=channels, pillow_ids=pillow_ids)
        return [row(), row("call", phone=None)]

    async def fake_finish(db, nid, status, ref, error):
        finished.append((status, ref, error))

    async def fake_log(db, pillow_id, agent, intent, **kw):
        logged.append((pillow_id, intent))

    monkeypatch.setattr(sender_module, "list_sendable_notifications", fake_list)
    monkeypatch.setattr(sender_module, "finish_notification", fake_finish)
    monkeypatch.setattr(sender_module, "log_action", fake_log)
    asyncio.run(NotificationSender(FakeIMessage(), FakeTwilio(), ["mum"]).tick(None))
    assert asked == {"channels": ["sms", "call"], "pillow_ids": ["mum"]}
    assert finished == [("sent", "imessage:guid-1", None), ("failed", None, "no phone number on record")]
    assert logged == [("mum", "Texted (iMessage) Sarah"),
                      ("mum", "Could not call Sarah: no phone number on record")]


# ---------- a call that doesn't reach a person ----------

def follow(monkeypatch, tw, r):
    logged = []

    async def fake_log(db, pillow_id, agent, intent, **kw):
        logged.append((pillow_id, intent))

    monkeypatch.setattr(sender_module, "log_action", fake_log)
    monkeypatch.setattr(sender_module, "CALL_POLL_S", 0)
    asyncio.run(NotificationSender(FakeIMessage("down"), tw, ["mum"]).follow_call(None, r, "CA1"))
    return logged


def test_rejected_call_is_followed_by_a_text(monkeypatch):
    tw = FakeTwilio(outcome=[("ringing", None), ("busy", None)])
    logged = follow(monkeypatch, tw, row("call"))
    assert tw.texts == [(PHONE, "Margaret hasn't come back to bed.")]
    assert logged == [("mum", "Sarah rejected the call, so texted them (SMS)")]


def test_voicemail_counts_as_not_reached(monkeypatch):
    tw = FakeTwilio(outcome=[("in-progress", "machine_start")])
    logged = follow(monkeypatch, tw, row("call"))
    assert logged == [("mum", "Sarah didn't pick up (voicemail), so texted them (SMS)")]


def test_unanswered_call_without_text_consent_says_so(monkeypatch):
    tw = FakeTwilio(outcome=[("no-answer", None)])
    logged = follow(monkeypatch, tw, row("call", consent=False))
    assert tw.texts == []
    assert logged == [("mum", "Sarah didn't answer; no text either (has not agreed to texts)")]


def test_answered_call_sends_nothing_more(monkeypatch):
    tw = FakeTwilio(outcome=[("ringing", None), ("in-progress", "human")])
    assert follow(monkeypatch, tw, row("call")) == [] and tw.texts == []


# ---------- the HTTP clients ----------

def test_twilio_sms_and_call_requests():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, parse_qs(request.content.decode())))
        return httpx.Response(201, json={"sid": "SM9"})

    tw = Twilio("AC1", "tok", "+15550000000", http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert asyncio.run(tw.sms(PHONE, "hi")) == "SM9"
    asyncio.run(tw.call(PHONE, "Mum & Dad <now>"))
    assert seen[0] == ("/2010-04-01/Accounts/AC1/Messages.json",
                       {"To": [PHONE], "From": ["+15550000000"], "Body": ["hi"]})
    assert seen[1][0].endswith("/Calls.json") and "Mum &amp; Dad &lt;now&gt;" in seen[1][1]["Twiml"][0]
    assert seen[1][1]["MachineDetection"] == ["Enable"] and seen[1][1]["Timeout"] == ["25"]


def test_twilio_call_status():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/2010-04-01/Accounts/AC1/Calls/CA9.json"
        return httpx.Response(200, json={"sid": "CA9", "status": "busy", "answered_by": None})

    tw = Twilio("AC1", "tok", "+15550000000", http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert asyncio.run(tw.call_status("CA9")) == ("busy", None)


def test_twilio_error_becomes_delivery_error():
    def handler(request):
        return httpx.Response(400, json={"message": "The 'To' number is not verified"})

    tw = Twilio("AC1", "tok", "+1555", http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(DeliveryError, match="400: The 'To' number is not verified"):
        asyncio.run(tw.sms(PHONE, "hi"))


def test_imessage_client_posts_to_the_sidecar():
    def handler(request):
        assert request.url.path == "/send"
        return httpx.Response(200, json={"id": "g1"}) if b"+1555" in request.content else \
            httpx.Response(503, json={"error": "not set"})

    im = IMessage("http://imessage:8787/", http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert asyncio.run(im.send(PHONE, "hi")) == "g1"
    with pytest.raises(DeliveryError, match="503: not set"):
        asyncio.run(im.send("+4420", "hi"))


# ---------- queueing before the migration is applied ----------

class _Table:
    def __init__(self, inserts):
        self.inserts = inserts

    def insert(self, row):
        self.inserts.append(dict(row))
        self.row = row
        return self

    async def execute(self):
        from postgrest.exceptions import APIError
        if "message" in self.row:
            raise APIError({"code": "PGRST204", "message": "Could not find the 'message' column"})


def test_queues_without_the_words_until_the_column_exists():
    from app.crud.night_log import add_notification

    inserts = []
    db = type("Db", (), {"table": lambda self, name: _Table(inserts)})()
    asyncio.run(add_notification(db, 3, "c1", "sms", "words"))
    assert inserts == [{"incident_id": 3, "contact_id": "c1", "channel": "sms", "message": "words"},
                       {"incident_id": 3, "contact_id": "c1", "channel": "sms"}]
