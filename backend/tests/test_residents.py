"""Resident settings API ("when it watches", "before telling family"): offline checks, then live Supabase.

The live tests only touch the test resident (the owner of `test-pillow`), never `mum`'s household.
"""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from supabase import Client

from app.core.app_constants import FAMILY_APP_AGENT
from app.crud.crud_constants import AGENT_LOG_TABLE, RESIDENTS_TABLE
from app.schemas.account import TIMEOUT_MAX, TIMEOUT_MIN, CheckinWaitUpdate, WatchHours
from tests.seed_constants import TEST_PILLOW_ID, TEST_RESIDENT_ID, UNKNOWN_RESIDENT_ID

WATCH_URL = f"/api/residents/{TEST_RESIDENT_ID}/watch-hours"
WAIT_URL = f"/api/residents/{TEST_RESIDENT_ID}/checkin-wait"
NEW_HOURS = {"quiet_start": "21:30", "quiet_end": "06:45"}
BAD_TIMES = ["25:00", "noon", ""]


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _stored(db: Client, *columns: str) -> dict:
    """The test resident's columns as Supabase holds them."""
    return (
        db.table(RESIDENTS_TABLE).select(",".join(columns)).eq("id", TEST_RESIDENT_ID).single().execute().data
    )


def _latest_app_log(db: Client) -> dict:
    """The newest agent_log row the family app wrote on the test pillow."""
    rows = (
        db.table(AGENT_LOG_TABLE)
        .select("intent, tool, args")
        .eq("pillow_id", TEST_PILLOW_ID)
        .eq("agent", FAMILY_APP_AGENT)
        .order("ts", desc=True)
        .limit(1)
        .execute()
        .data
    )
    return rows[0]


# ---------- offline ----------


@pytest.mark.parametrize("url", [WATCH_URL, WAIT_URL])
def test_resident_settings_need_a_valid_login(offline_client: TestClient, url: str):
    assert offline_client.get(url).status_code == 401
    assert offline_client.put(url, json={}, headers=_bearer("not-a-real-token")).status_code == 401


def test_checkin_wait_keeps_the_guardian_bounds():
    for minutes in (TIMEOUT_MIN - 1, TIMEOUT_MAX + 1):
        with pytest.raises(ValidationError):
            CheckinWaitUpdate(checkin_timeout_min=minutes)
    assert CheckinWaitUpdate(checkin_timeout_min=TIMEOUT_MIN).checkin_timeout_min == TIMEOUT_MIN


def test_watch_hours_read_and_write_hh_mm():
    assert WatchHours(quiet_start="21:30:00", quiet_end="06:45").model_dump(mode="json") == NEW_HOURS
    for bad in BAD_TIMES:
        with pytest.raises(ValidationError):
            WatchHours(quiet_start=bad, quiet_end="06:45")


# ---------- live Supabase (test resident only) ----------


def test_owner_sets_watch_hours(client: TestClient, db: Client, owner_token: str):
    changed = client.put(WATCH_URL, json=NEW_HOURS, headers=_bearer(owner_token))
    assert changed.status_code == 200 and changed.json() == NEW_HOURS
    assert client.get(WATCH_URL, headers=_bearer(owner_token)).json() == NEW_HOURS
    assert _stored(db, "quiet_start", "quiet_end") == {"quiet_start": "21:30:00", "quiet_end": "06:45:00"}
    assert _latest_app_log(db) == {"intent": "change settings", "tool": "watch_hours", "args": NEW_HOURS}


def test_equal_watch_hours_are_kept_as_watch_all_day(client: TestClient, owner_token: str):
    all_day = {"quiet_start": "00:00", "quiet_end": "00:00"}
    assert client.put(WATCH_URL, json=all_day, headers=_bearer(owner_token)).status_code == 200
    assert client.get(WATCH_URL, headers=_bearer(owner_token)).json() == all_day


def test_owner_sets_checkin_wait(client: TestClient, db: Client, owner_token: str):
    changed = client.put(WAIT_URL, json={"checkin_timeout_min": 25}, headers=_bearer(owner_token))
    assert changed.status_code == 200 and changed.json() == {"checkin_timeout_min": 25}
    assert client.get(WAIT_URL, headers=_bearer(owner_token)).json() == {"checkin_timeout_min": 25}
    assert _stored(db, "checkin_timeout_min") == {"checkin_timeout_min": 25}
    assert _latest_app_log(db)["tool"] == "checkin_wait"


@pytest.mark.parametrize("minutes", [TIMEOUT_MIN - 1, TIMEOUT_MAX + 1, "soon"])
def test_checkin_wait_outside_the_bounds_is_422(client: TestClient, db: Client, owner_token: str, minutes):
    before = _stored(db, "checkin_timeout_min")
    response = client.put(WAIT_URL, json={"checkin_timeout_min": minutes}, headers=_bearer(owner_token))
    assert response.status_code == 422
    assert _stored(db, "checkin_timeout_min") == before


@pytest.mark.parametrize("bad", BAD_TIMES)
def test_watch_hours_with_a_bad_time_is_422(client: TestClient, db: Client, owner_token: str, bad: str):
    before = _stored(db, "quiet_start", "quiet_end")
    response = client.put(
        WATCH_URL, json={"quiet_start": bad, "quiet_end": "06:45"}, headers=_bearer(owner_token)
    )
    assert response.status_code == 422
    assert _stored(db, "quiet_start", "quiet_end") == before


@pytest.mark.parametrize("url", [WATCH_URL, WAIT_URL])
def test_a_plain_contact_reads_and_changes(client: TestClient, contact_token: str, url: str):
    assert client.get(url, headers=_bearer(contact_token)).status_code == 200
    body = NEW_HOURS if url == WATCH_URL else {"checkin_timeout_min": 25}
    assert client.put(url, json=body, headers=_bearer(contact_token)).status_code == 200


@pytest.mark.parametrize("url", [WATCH_URL, WAIT_URL])
def test_a_login_that_does_not_look_after_her_gets_403(client: TestClient, stranger_token: str, url: str):
    assert client.get(url, headers=_bearer(stranger_token)).status_code == 403
    body = NEW_HOURS if url == WATCH_URL else {"checkin_timeout_min": 25}
    assert client.put(url, json=body, headers=_bearer(stranger_token)).status_code == 403


@pytest.mark.parametrize("setting", ["watch-hours", "checkin-wait"])
def test_unknown_resident_is_404_and_a_malformed_id_422(client: TestClient, owner_token: str, setting: str):
    auth = _bearer(owner_token)
    assert client.get(f"/api/residents/{UNKNOWN_RESIDENT_ID}/{setting}", headers=auth).status_code == 404
    assert client.get(f"/api/residents/not-a-uuid/{setting}", headers=auth).status_code == 422
