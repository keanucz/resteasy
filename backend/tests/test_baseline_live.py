"""The night baseline end to end on the seeded test pillow (live Supabase; skipped without it).

A week of short trips is written for test-pillow, then GET /night reports the baseline and Night
Watch checks in at the learned wait instead of 20 min. Every row written for test-pillow is deleted
before and after; the real `mum` pillow is never touched.
"""

import time as clock
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from supabase import Client

from app.agents.night_summary import last_night_window
from app.crud.crud_constants import (
    AGENT_LOG_TABLE,
    COMMANDS_TABLE,
    EVENTS_TABLE,
    INCIDENTS_TABLE,
    PILLOW_STATE_TABLE,
    RESIDENTS_TABLE,
)
from tests.seed_constants import TEST_PILLOW_ID, TEST_RESIDENT_ID

TZ = "America/Los_Angeles"  # the test resident's timezone (the residents default)
TRIP_MIN = 7  # her usual trip, so the learned wait is 7 + 5 = 12 min
LEARNED = TRIP_MIN + 5
NIGHT = datetime(2026, 10, 24, 23, 0, tzinfo=ZoneInfo(TZ))  # inside her quiet hours
STATE_URL = f"/api/pillows/{TEST_PILLOW_ID}/state"


def _clean(db: Client) -> None:
    for table in (EVENTS_TABLE, COMMANDS_TABLE, INCIDENTS_TABLE, AGENT_LOG_TABLE):
        db.table(table).delete().eq("pillow_id", TEST_PILLOW_ID).execute()
    db.table(PILLOW_STATE_TABLE).update({"night_state": "awake"}).eq("pillow_id", TEST_PILLOW_ID).execute()


def _seed_week(db: Client, night_start: datetime) -> None:
    """One 7-minute trip at 02:00 on each of the 6 nights before `night_start`."""
    rows = []
    for k in range(1, 7):
        left = night_start - timedelta(days=k) + timedelta(hours=8)  # 18:00 + 8 h = 02:00
        for kind, at in (("bed_exit", left), ("bed_return", left + timedelta(minutes=TRIP_MIN))):
            rows.append({"pillow_id": TEST_PILLOW_ID, "event_type": kind,
                         "device_ts": at.astimezone(UTC).isoformat(), "data": {"seed": "baseline_test"}})
    db.table(EVENTS_TABLE).insert(rows).execute()


def _owner_wait(db: Client) -> int:
    rows = db.table(RESIDENTS_TABLE).select("checkin_timeout_min").eq("id", TEST_RESIDENT_ID).execute().data
    return rows[0]["checkin_timeout_min"]


@pytest.fixture
def week(db: Client, live_client: TestClient) -> Iterator[TestClient]:
    _clean(db)
    yield live_client
    _clean(db)


def test_night_report_shows_the_learned_baseline(db: Client, week: TestClient) -> None:
    night_start, _ = last_night_window(clock.time(), TZ)
    _seed_week(db, night_start)
    baseline = week.get(f"/api/pillows/{TEST_PILLOW_ID}/night").json()["summary"]["baseline"]
    assert baseline["mode"] == "learned" and baseline["usual_trip_min"] == TRIP_MIN
    assert baseline["learned_timeout_min"] == LEARNED
    assert baseline["checkin_timeout_min"] == min(_owner_wait(db), LEARNED)


def test_night_watch_checks_in_at_the_learned_wait(db: Client, week: TestClient) -> None:
    _seed_week(db, NIGHT.replace(hour=18))
    wait = min(_owner_wait(db), LEARNED)
    t0 = NIGHT.timestamp()

    def report(seconds: float, head_on: bool) -> None:
        body = {"pillow_id": TEST_PILLOW_ID, "ts": t0 + seconds, "head_on": head_on, "motion": 0.05,
                "room_motion": False, "light": 0.02, "keys": {"fine": False}}
        assert week.post(STATE_URL, json=body).status_code == 200

    report(0, True)
    report(6, True)  # lay_down
    report(60, False)
    report(91, False)  # bed_exit, left at 60 s
    report(60 + (wait - 1) * 60, False)
    assert week.get(STATE_URL).json()["night_state"] == "up"
    report(60 + wait * 60, False)
    assert week.get(STATE_URL).json()["night_state"] == "check_in"

    log = db.table(AGENT_LOG_TABLE).select("intent, tool").eq("pillow_id", TEST_PILLOW_ID).execute().data
    assert any(r["tool"] == "baseline" and r["intent"].startswith(f"check-in wait {wait} min") for r in log)


def test_a_restart_does_not_log_the_same_wait_again(db: Client, week: TestClient) -> None:
    """Each deploy restarts the backend; the learned wait is logged once, not once per restart."""
    from app.main import app

    _seed_week(db, NIGHT.replace(hour=18))
    body = {"pillow_id": TEST_PILLOW_ID, "ts": NIGHT.timestamp(), "head_on": False, "motion": 0.05,
            "room_motion": False, "light": 0.02, "keys": {"fine": False}}

    def baseline_rows() -> int:
        rows = db.table(AGENT_LOG_TABLE).select("tool").eq("pillow_id", TEST_PILLOW_ID).execute().data
        return sum(r["tool"] == "baseline" for r in rows)

    assert week.post(STATE_URL, json=body).status_code == 200
    assert baseline_rows() == 1
    with TestClient(app) as restarted:  # a fresh lifespan: a new WatchService with no memory
        assert restarted.post(STATE_URL, json=dict(body, ts=body["ts"] + 1)).status_code == 200
    assert baseline_rows() == 1
