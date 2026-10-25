"""Night Watch end to end through the API on the seeded test pillow (live Supabase; skipped without it).

One night: lies down, gets up, doesn't come back, the check-in escalates, then she's back in bed.
Everything it writes for test-pillow is deleted afterwards and its night state reset.
"""

from collections.abc import Iterator
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from supabase import Client

from app.core.config import get_settings
from app.crud.crud_constants import (
    AGENT_LOG_TABLE,
    COMMANDS_TABLE,
    EVENTS_TABLE,
    INCIDENTS_TABLE,
    NOTIFICATIONS_TABLE,
    PILLOW_STATE_TABLE,
)
from app.notify.notify_constants import AGENT as NOTIFY_AGENT
from tests.seed_constants import TEST_PILLOW_ID, TEST_USER_ID, UNKNOWN_CONTACT_ID

# 23:00 in the test resident's timezone (the residents default), inside her quiet hours
NIGHT = datetime(2026, 10, 24, 23, 0, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp()
STATE_URL = f"/api/pillows/{TEST_PILLOW_ID}/state"
CHECKIN_TOKEN = "test-checkin-token"


def _clean(db: Client) -> None:
    """Remove everything Night Watch wrote for the test pillow (notifications go with incidents)."""
    for table in (EVENTS_TABLE, COMMANDS_TABLE, INCIDENTS_TABLE, AGENT_LOG_TABLE):
        db.table(table).delete().eq("pillow_id", TEST_PILLOW_ID).execute()
    db.table(PILLOW_STATE_TABLE).update({"night_state": "awake"}).eq("pillow_id", TEST_PILLOW_ID).execute()


@pytest.fixture
def night(db: Client, live_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """A live client with the test pillow's night history cleared before and after."""
    monkeypatch.setattr(get_settings(), "checkin_token", CHECKIN_TOKEN)
    _clean(db)
    yield live_client
    _clean(db)


def _report(client: TestClient, seconds: float, head_on: bool) -> None:
    """Post one state report `seconds` after 23:00."""
    body = {"pillow_id": TEST_PILLOW_ID, "ts": NIGHT + seconds, "head_on": head_on, "motion": 0.05,
            "room_motion": False, "light": 0.02, "keys": {"fine": False}}
    assert client.post(STATE_URL, json=body).status_code == 200


def _rows(db: Client, table: str, columns: str = "*") -> list[dict]:
    return db.table(table).select(columns).eq("pillow_id", TEST_PILLOW_ID).order("id").execute().data


def _escalate(client: TestClient) -> None:
    """Lies down, gets up, doesn't return for 20 min, and the check-in escalates."""
    _report(client, 0, True)
    _report(client, 6, True)  # head on 5 s: lay_down
    _report(client, 60, False)
    _report(client, 91, False)  # head off 30 s: bed_exit
    _report(client, 60 + 20 * 60, False)  # 20 min since she left: check-in
    assert client.get(STATE_URL).json()["night_state"] == "check_in"
    checkin_url = f"/api/pillows/{TEST_PILLOW_ID}/checkin"
    result = {"escalate": True, "reason": "She didn't answer."}
    assert client.post(checkin_url, json=result).status_code == 401  # only the base laptop may
    escalated = client.post(checkin_url, json=result, headers={"Authorization": f"Bearer {CHECKIN_TOKEN}"})
    assert escalated.json() == {"night_state": "escalating"}


def test_a_night_with_no_return_escalates_and_resolves(db: Client, night: TestClient) -> None:
    """Lies down, gets up, doesn't return, check-in escalates, back in bed: all stored."""
    _escalate(night)

    _report(night, 1300, True)
    _report(night, 1346, True)  # head on 45 s: back in bed
    assert night.get(STATE_URL).json()["night_state"] == "in_bed"

    events = [e["event_type"] for e in _rows(db, EVENTS_TABLE, "id, event_type")]
    assert events == ["lay_down", "bed_exit", "no_return", "checkin_result", "escalation_step", "bed_return"]

    lights = [c["args"]["brightness_pct"] for c in _rows(db, COMMANDS_TABLE, "id, cmd, args")
              if c["cmd"] == "set_light"]
    assert lights == [20, 0]  # path light on, then off

    (incident,) = _rows(db, INCIDENTS_TABLE)
    assert incident["status"] == "resolved" and incident["step"] == 1 and incident["resolved_at"]
    notes = db.table(NOTIFICATIONS_TABLE).select("channel").eq("incident_id", incident["id"]).execute().data
    assert [n["channel"] for n in notes] == ["app", "sms"]  # the in-app alert, then "back in bed"

    log = _rows(db, AGENT_LOG_TABLE, "id, agent, intent")
    # Night Watch's decisions, plus the notification sender's delivery notes (app/notify, #53)
    assert {row["agent"] for row in log} <= {"night_watch", NOTIFY_AGENT}
    assert any(row["intent"] == "check_in -> escalating" for row in log)


def test_im_on_it_in_the_app_acknowledges_and_stops_the_alerts(db: Client, night: TestClient) -> None:
    """The app's "I'm on it" marks the incident acknowledged by that contact; strangers get a 404."""
    _escalate(night)
    ack_url = f"/api/pillows/{TEST_PILLOW_ID}/ack"
    assert night.post(ack_url, json={"contact_id": UNKNOWN_CONTACT_ID}).status_code == 404
    assert night.post(ack_url, json={"contact_id": TEST_USER_ID}).json() == {"night_state": "escalating"}

    (incident,) = _rows(db, INCIDENTS_TABLE)
    assert incident["status"] == "acknowledged" and incident["acked_by"] == TEST_USER_ID
    _report(night, 60 + 30 * 60, False)  # 10 more minutes: the ladder must not move on
    notes = db.table(NOTIFICATIONS_TABLE).select("channel").eq("incident_id", incident["id"]).execute().data
    assert [n["channel"] for n in notes] == ["app"]
    said = [r["intent"] for r in _rows(db, AGENT_LOG_TABLE, "id, intent")]
    assert "Test knows, and is checking on you." in said
