"""The Fetch.ai agents' own tokens and a family member's writes (settings, goodnight, away nights).

Offline: who may call what, before the database is read. Live: the writes on the test resident and
her test pillow only, never `mum`, with every change put back afterwards.
"""

from collections.abc import Iterator
from contextlib import suppress
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError
from supabase import Client

from app.core.app_constants import (
    AGENT_CONTACT_MISMATCH,
    AGENT_CONTACT_NOT_LINKED,
    AGENT_OWN_TOKEN,
    FAMILY_AGENT,
)
from app.core.config import get_settings
from app.crud.crud_constants import (
    AGENT_LOG_TABLE,
    CONTACT_AWAY_TABLE,
    CONTACTS_TABLE,
    EVENTS_TABLE,
    RESIDENT_CONTACTS_TABLE,
    RESIDENTS_TABLE,
)
from tests.seed_constants import (
    TEST_HELPER_PRIORITY,
    TEST_PILLOW_ID,
    TEST_RESIDENT_ID,
    TEST_USER_ID,
    UNKNOWN_CONTACT_ID,
)

BASE = f"/api/pillows/{TEST_PILLOW_ID}"
SHARED, COORDINATOR = "test-shared-token", "test-coordinator-token"
OWNER_AGENT, HELPER_AGENT, STRANGER_AGENT = "test-owner-agent", "test-helper-agent", "test-stranger-agent"
RESIDENT_KEYS = ("quiet_start", "quiet_end", "checkin_timeout_min")


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def tokens(monkeypatch: pytest.MonkeyPatch) -> dict[UUID, str]:
    """Known agent tokens: the shared one, the coordinator's, and the owner's family agent's.
    Tests add more family agents to the returned dict."""
    settings = get_settings()
    family = {UUID(TEST_USER_ID): OWNER_AGENT, UUID(UNKNOWN_CONTACT_ID): STRANGER_AGENT}
    monkeypatch.setattr(settings, "checkin_token", SHARED)
    monkeypatch.setattr(settings, "coordinator_token", COORDINATOR)
    monkeypatch.setattr(settings, "family_agent_tokens", family)
    return family


# ---------- offline: who may call what ----------


def test_family_writes_need_a_login_or_an_agent(offline_client: TestClient, tokens: dict):
    calls = [
        offline_client.patch(f"{BASE}/settings", json={"checkin_timeout_min": 20}),
        offline_client.post(f"{BASE}/goodnight", json={"message": "Night night", "from_name": "Ellie"}),
        offline_client.get(f"{BASE}/away"),
        offline_client.post(f"{BASE}/away", json={"from_date": "2026-11-01", "until_date": "2026-11-02"}),
        offline_client.delete(f"{BASE}/away"),
    ]
    assert [r.status_code for r in calls] == [401] * 5


def test_a_family_agent_speaks_only_for_its_own_contact(offline_client: TestClient, tokens: dict):
    other = offline_client.get(f"{BASE}/away?contact_id={UNKNOWN_CONTACT_ID}", headers=_bearer(OWNER_AGENT))
    assert (other.status_code, other.json()["detail"]) == (403, AGENT_CONTACT_MISMATCH)


def test_the_shared_token_stops_acting_for_family_once_they_have_their_own(
    offline_client: TestClient, tokens: dict
):
    response = offline_client.get(f"{BASE}/away?contact_id={TEST_USER_ID}", headers=_bearer(SHARED))
    assert (response.status_code, response.json()["detail"]) == (403, AGENT_OWN_TOKEN)


def test_only_the_coordinator_sets_the_roster(offline_client: TestClient, tokens: dict):
    off = {"on_call": False, "reason": "away"}
    url = f"{BASE}/roster/{TEST_USER_ID}"
    assert offline_client.put(url, json=off).status_code == 401
    assert offline_client.put(url, json=off, headers=_bearer(OWNER_AGENT)).status_code == 403
    assert offline_client.put(url, json=off, headers=_bearer(SHARED)).status_code == 403
    assert offline_client.get(f"{BASE}/roster").status_code == 401


# ---------- live ----------


@pytest.fixture
def family_client(db: Client, client: TestClient, tokens: dict) -> Iterator[TestClient]:
    """A live client with the agent tokens; the test resident's settings, the test pillow's
    goodnight events and family log rows, and the test contacts' away nights are put back after."""
    resident = db.table(RESIDENTS_TABLE).select("*").eq("id", TEST_RESIDENT_ID).single().execute().data
    yield client
    restore = {k: resident[k] for k in RESIDENT_KEYS}
    db.table(RESIDENTS_TABLE).update(restore).eq("id", TEST_RESIDENT_ID).execute()
    events = db.table(EVENTS_TABLE).delete().eq("pillow_id", TEST_PILLOW_ID)
    events.eq("event_type", "goodnight_queued").execute()
    db.table(AGENT_LOG_TABLE).delete().eq("pillow_id", TEST_PILLOW_ID).eq("agent", FAMILY_AGENT).execute()
    with suppress(APIError):  # the contact_away migration may not be applied yet
        db.table(CONTACT_AWAY_TABLE).delete().eq("contact_id", TEST_USER_ID).execute()


@pytest.fixture
def helper(db: Client, tokens: dict) -> Iterator[str]:
    """A plain (not owner) contact of the test resident with a family agent of its own."""
    contact_id = db.table(CONTACTS_TABLE).insert({"full_name": "Agent Helper"}).execute().data[0]["id"]
    link = {"resident_id": TEST_RESIDENT_ID, "contact_id": contact_id, "priority": TEST_HELPER_PRIORITY}
    tokens[UUID(contact_id)] = HELPER_AGENT
    try:
        db.table(RESIDENT_CONTACTS_TABLE).insert(link).execute()
        yield contact_id
    finally:
        db.table(CONTACTS_TABLE).delete().eq("id", contact_id).execute()  # cascades to the link


def _resident(db: Client) -> dict:
    return db.table(RESIDENTS_TABLE).select("*").eq("id", TEST_RESIDENT_ID).single().execute().data


def _family_log(db: Client, tool: str) -> list[dict]:
    rows = db.table(AGENT_LOG_TABLE).select("intent, args").eq("pillow_id", TEST_PILLOW_ID)
    return rows.eq("agent", FAMILY_AGENT).eq("tool", tool).order("id").execute().data


def test_any_care_circle_agent_changes_settings_within_the_apps_bounds(
    family_client: TestClient, db: Client, helper: str
):
    patch = {"checkin_timeout_min": 25, "quiet_start": "22:30", "quiet_end": None}
    response = family_client.patch(f"{BASE}/settings", json=patch, headers=_bearer(HELPER_AGENT))
    assert response.json() == {"applied": {"checkin_timeout_min": 25, "quiet_start": "22:30"}}
    stored = _resident(db)
    assert (stored["checkin_timeout_min"], stored["quiet_start"][:5]) == (25, "22:30")
    assert [row["intent"] for row in _family_log(db, "settings")] == ["change settings for Agent Helper"]

    too_long = family_client.patch(f"{BASE}/settings", json={"checkin_timeout_min": 45},
                                   headers=_bearer(OWNER_AGENT))
    assert too_long.status_code == 422
    assert _resident(db)["checkin_timeout_min"] == 25


def test_an_agent_for_someone_outside_her_care_circle_changes_nothing(family_client: TestClient, db: Client):
    before = _resident(db)["checkin_timeout_min"]
    response = family_client.patch(f"{BASE}/settings", json={"checkin_timeout_min": 11},
                                   headers=_bearer(STRANGER_AGENT))
    assert (response.status_code, response.json()["detail"]) == (403, AGENT_CONTACT_NOT_LINKED)
    assert _resident(db)["checkin_timeout_min"] == before


def test_a_goodnight_names_who_sent_it(family_client: TestClient, db: Client):
    msg = {"message": "Sleep well, Gran", "from_name": "Ellie"}
    assert family_client.post(f"{BASE}/goodnight", json=msg, headers=_bearer(OWNER_AGENT)).status_code == 201
    assert family_client.get(f"{BASE}/goodnight").json() == msg
    logged = _family_log(db, "goodnight")
    assert [row["intent"] for row in logged] == ["goodnight from Ellie for Test User"]
    assert logged[0]["args"]["contact_id"] == TEST_USER_ID


@pytest.fixture
def away_table(db: Client) -> None:
    try:
        db.table(CONTACT_AWAY_TABLE).select("id").limit(1).execute()
    except APIError:
        pytest.skip("contact_away migration not applied yet")


def test_away_nights_are_each_family_members_own(
    family_client: TestClient, db: Client, helper: str, away_table: None
):
    owner = _bearer(OWNER_AGENT)
    mine = {"from_date": "2099-01-01", "until_date": "2099-01-04", "note": "in Denver"}
    made = family_client.post(f"{BASE}/away", json=mine, headers=owner)
    assert made.status_code == 201
    assert family_client.get(f"{BASE}/away", headers=owner).json() == [{**mine, "id": made.json()["id"]}]
    assert family_client.get(f"{BASE}/away", headers=_bearer(HELPER_AGENT)).json() == []
    backwards = {"from_date": "2099-01-04", "until_date": "2099-01-01"}
    assert family_client.post(f"{BASE}/away", json=backwards, headers=owner).status_code == 422
    assert [row["intent"] for row in _family_log(db, "away")] == [
        "away 2099-01-01 to 2099-01-04 (in Denver) for Test User"
    ]
    assert family_client.delete(f"{BASE}/away", headers=owner).status_code == 204
    assert family_client.get(f"{BASE}/away", headers=owner).json() == []


def test_the_coordinator_and_family_agents_read_the_roster(family_client: TestClient):
    for token in (COORDINATOR, OWNER_AGENT, SHARED):
        roster = family_client.get(f"{BASE}/roster", headers=_bearer(token))
        assert TEST_USER_ID in [c["contact_id"] for c in roster.json()["contacts"]]
