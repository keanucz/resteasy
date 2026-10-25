"""The evening watch roster: the Guardian's on-call rule offline, then the endpoints on live Supabase.

The live tests only touch the test resident's contacts (plus a throwaway helper), never `mum`'s.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from supabase import Client

from app.agents.guardian import Guardian
from app.core.config import get_settings
from app.crud.crud_constants import AGENT_LOG_TABLE, CONTACTS_TABLE, RESIDENT_CONTACTS_TABLE
from app.routers.family import ROSTER_AGENT
from tests.seed_constants import (
    TEST_HELPER_PRIORITY,
    TEST_PILLOW_ID,
    TEST_RESIDENT_ID,
    TEST_USER_ID,
    UNKNOWN_CONTACT_ID,
)

TOKEN = "test-roster-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
ROSTER_URL = f"/api/pillows/{TEST_PILLOW_ID}/roster"


# ---------- offline: the Guardian ----------


def test_last_on_call_contact_cannot_go_off_call():
    contacts = [{"id": "a", "on_call": True}, {"id": "b", "on_call": False}]
    verdict = Guardian().check_on_call(contacts, "a", on_call=False)
    assert not verdict.allowed
    assert "nobody on call" in verdict.reason


def test_a_contact_can_go_off_call_while_another_is_on():
    contacts = [{"id": "a", "on_call": True}, {"id": "b", "on_call": True}]
    assert Guardian().check_on_call(contacts, "a", on_call=False).allowed


def test_going_on_call_is_always_allowed():
    assert Guardian().check_on_call([{"id": "a", "on_call": False}], "a", on_call=True).allowed


# ---------- live ----------


@pytest.fixture
def roster_client(db: Client, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """A live client with a known agent token; the test resident's on-call flags and the roster's
    agent_log rows are put back afterwards."""
    monkeypatch.setattr(get_settings(), "checkin_token", TOKEN)
    yield client
    db.table(CONTACTS_TABLE).update({"on_call": True}).eq("id", TEST_USER_ID).execute()
    db.table(AGENT_LOG_TABLE).delete().eq("pillow_id", TEST_PILLOW_ID).eq("agent", ROSTER_AGENT).execute()


@pytest.fixture
def helper_id(db: Client) -> Iterator[str]:
    """A second, throwaway contact of the test resident (on call), deleted afterwards."""
    contact_id = db.table(CONTACTS_TABLE).insert({"full_name": "Roster Helper"}).execute().data[0]["id"]
    link = {"resident_id": TEST_RESIDENT_ID, "contact_id": contact_id, "priority": TEST_HELPER_PRIORITY}
    try:
        db.table(RESIDENT_CONTACTS_TABLE).insert(link).execute()
        yield contact_id
    finally:
        db.table(CONTACTS_TABLE).delete().eq("id", contact_id).execute()  # cascades to the link


def test_roster_needs_the_agent_token(roster_client: TestClient):
    assert roster_client.get(ROSTER_URL).status_code == 401
    off = {"on_call": False, "reason": "away"}
    assert roster_client.put(f"{ROSTER_URL}/{TEST_USER_ID}", json=off).status_code == 401


def test_roster_lists_contacts_in_alert_order(roster_client: TestClient, helper_id: str):
    roster = roster_client.get(ROSTER_URL, headers=AUTH).json()
    assert roster["timezone"]
    assert [c["contact_id"] for c in roster["contacts"]] == [TEST_USER_ID, helper_id]
    assert all(c["on_call"] for c in roster["contacts"])


def test_off_call_is_stored_and_logged(roster_client: TestClient, db: Client, helper_id: str):
    off = {"on_call": False, "reason": "in Denver until Sunday"}
    result = roster_client.put(f"{ROSTER_URL}/{helper_id}", json=off, headers=AUTH).json()
    assert result == {"contact_id": helper_id, "on_call": False, "guardian": "allowed", "reason": None}
    stored = db.table(CONTACTS_TABLE).select("on_call").eq("id", helper_id).single().execute().data
    assert stored["on_call"] is False
    log = db.table(AGENT_LOG_TABLE).select("intent, guardian").eq("pillow_id", TEST_PILLOW_ID)
    rows = log.eq("agent", ROSTER_AGENT).order("ts", desc=True).limit(1).execute().data
    assert rows[0]["guardian"] == "allowed"
    assert "in Denver until Sunday" in rows[0]["intent"]


def test_the_last_on_call_contact_stays_on_call(roster_client: TestClient, db: Client, helper_id: str):
    off = {"on_call": False, "reason": "busy"}
    roster_client.put(f"{ROSTER_URL}/{helper_id}", json=off, headers=AUTH)
    result = roster_client.put(f"{ROSTER_URL}/{TEST_USER_ID}", json=off, headers=AUTH).json()
    assert result["guardian"] == "blocked"
    assert result["on_call"] is True
    stored = db.table(CONTACTS_TABLE).select("on_call").eq("id", TEST_USER_ID).single().execute().data
    assert stored["on_call"] is True


def test_unknown_contact_is_404(roster_client: TestClient):
    off = {"on_call": False, "reason": "away"}
    assert roster_client.put(f"{ROSTER_URL}/{UNKNOWN_CONTACT_ID}", json=off, headers=AUTH).status_code == 404
