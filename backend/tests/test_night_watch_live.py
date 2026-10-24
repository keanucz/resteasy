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

from app.crud.crud_constants import (
    AGENT_LOG_TABLE,
    COMMANDS_TABLE,
    EVENTS_TABLE,
    INCIDENTS_TABLE,
    NOTIFICATIONS_TABLE,
    PILLOW_STATE_TABLE,
)
from tests.seed_constants import TEST_PILLOW_ID

# 23:00 in the test resident's timezone (the residents default), inside her quiet hours
NIGHT = datetime(2026, 10, 24, 23, 0, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp()
STATE_URL = f"/api/pillows/{TEST_PILLOW_ID}/state"


def _clean(db: Client) -> None:
    """Remove everything Night Watch wrote for the test pillow (notifications go with incidents)."""
    for table in (EVENTS_TABLE, COMMANDS_TABLE, INCIDENTS_TABLE, AGENT_LOG_TABLE):
        db.table(table).delete().eq("pillow_id", TEST_PILLOW_ID).execute()
    db.table(PILLOW_STATE_TABLE).update({"night_state": "awake"}).eq("pillow_id", TEST_PILLOW_ID).execute()


@pytest.fixture
def night(db: Client, live_client: TestClient) -> Iterator[TestClient]:
    """A live client with the test pillow's night history cleared before and after."""
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


def test_a_night_with_no_return_escalates_and_resolves(db: Client, night: TestClient) -> None:
    """Lies down, gets up, doesn't return, check-in escalates, back in bed: all stored."""
    _report(night, 0, True)
    _report(night, 6, True)  # head on 5 s: lay_down
    _report(night, 60, False)
    _report(night, 91, False)  # head off 30 s: bed_exit
    _report(night, 60 + 20 * 60, False)  # 20 min since she left: check-in
    assert night.get(STATE_URL).json()["night_state"] == "check_in"

    escalated = night.post(f"/api/pillows/{TEST_PILLOW_ID}/checkin",
                           json={"escalate": True, "reason": "She didn't answer."})
    assert escalated.json() == {"night_state": "escalating"}

    _report(night, 1300, True)
    _report(night, 1306, True)  # back in bed
    assert night.get(STATE_URL).json()["night_state"] == "in_bed"

    events = [e["event_type"] for e in _rows(db, EVENTS_TABLE, "id, event_type")]
    assert events == ["lay_down", "bed_exit", "no_return", "checkin_result", "escalation_step", "bed_return"]

    lights = [c["args"]["brightness_pct"] for c in _rows(db, COMMANDS_TABLE, "id, cmd, args")
              if c["cmd"] == "set_light"]
    assert lights == [20, 0]  # path light on, then off

    (incident,) = _rows(db, INCIDENTS_TABLE)
    assert incident["status"] == "resolved" and incident["step"] == 1 and incident["resolved_at"]
    notes = db.table(NOTIFICATIONS_TABLE).select("channel").eq("incident_id", incident["id"]).execute().data
    assert [n["channel"] for n in notes] == ["sms", "sms"]  # the alert, then "back in bed"

    log = _rows(db, AGENT_LOG_TABLE, "id, agent, intent")
    assert all(row["agent"] == "night_watch" for row in log)
    assert any(row["intent"] == "check_in -> escalating" for row in log)
