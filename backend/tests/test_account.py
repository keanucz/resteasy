"""Account API: the app's own login, offline checks, then a round trip against live Supabase."""

import secrets
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from supabase import Client

from app.core.voice_constants import DEFAULT_VOICE_ID, VOICE_IDS
from app.crud.crud_constants import CONTACTS_TABLE, PILLOWS_TABLE, RESIDENTS_TABLE
from app.routers import account as account_router
from app.schemas.account import PreferencesPatch
from tests.conftest import _throwaway_login
from tests.seed_constants import TEST_PILLOW_ID, TEST_USER_ID

PREFS_URL = f"/api/pillows/{TEST_PILLOW_ID}/preferences"


# ---------- offline ----------


def test_voices_lists_the_offered_voices_with_skylar_first(client: TestClient):
    voices = client.get("/api/voices").json()
    assert voices[0]["id"] == DEFAULT_VOICE_ID and voices[0]["name"] == "Skylar"
    assert {v["id"] for v in voices} == VOICE_IDS


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer not-a-real-token"}])
def test_app_routes_need_a_valid_login(offline_client: TestClient, headers):
    assert offline_client.get("/api/me", headers=headers).status_code == 401
    assert offline_client.patch(PREFS_URL, json={}, headers=headers).status_code == 401


def test_patch_rejects_unknown_voices_and_out_of_bounds_timeouts():
    with pytest.raises(ValidationError):
        PreferencesPatch(voice_id="not-a-voice")
    with pytest.raises(ValidationError):
        PreferencesPatch(checkin_timeout_min=5)
    assert PreferencesPatch(checkin_timeout_min=25, quiet_start="22:30").model_dump(
        exclude_none=True, mode="json"
    ) == {
        "checkin_timeout_min": 25,
        "quiet_start": "22:30:00",
    }


# ---------- live Supabase (test-pillow only) ----------


def test_owner_reads_and_changes_preferences(client: TestClient, owner_token: str):
    auth = {"Authorization": f"Bearer {owner_token}"}
    me = client.get("/api/me", headers=auth).json()
    assert me["contact_id"] == TEST_USER_ID
    assert {"pillow_id": TEST_PILLOW_ID, "role": "owner"}.items() <= me["pillows"][0].items()

    voice = next(v for v in VOICE_IDS if v != DEFAULT_VOICE_ID)
    changed = client.patch(PREFS_URL, json={"voice_id": voice, "checkin_timeout_min": 25}, headers=auth)
    assert changed.status_code == 200
    assert client.get(PREFS_URL, headers=auth).json()["voice_id"] == voice
    assert client.get(PREFS_URL, headers=auth).json()["checkin_timeout_min"] == 25


def test_a_login_cannot_touch_a_pillow_it_does_not_look_after(client: TestClient, owner_token: str):
    auth = {"Authorization": f"Bearer {owner_token}"}
    assert (
        client.patch(
            "/api/pillows/mum/preferences", json={"monitoring_paused": True}, headers=auth
        ).status_code
        == 403
    )


@pytest.fixture
def fresh_signup(db: Client, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """A login that looks after nobody, with the demo pillow pointed at the test pillow; the contact
    it gets on joining is removed afterwards (deleting the login alone would leave it behind)."""
    monkeypatch.setattr(account_router, "DEMO_PILLOW_ID", TEST_PILLOW_ID)
    with _throwaway_login(db) as (user_id, token):
        try:
            yield token
        finally:
            db.table(CONTACTS_TABLE).delete().eq("user_id", user_id).execute()  # cascades to the link


def test_a_fresh_signup_joins_the_demo_household_once(client: TestClient, fresh_signup: str):
    auth = {"Authorization": f"Bearer {fresh_signup}"}
    assert client.get("/api/me", headers=auth).json()["pillows"] == []

    joined = client.post("/api/me/join-demo", headers=auth)
    assert joined.status_code == 200
    me = joined.json()
    assert me["contact_id"] and me["full_name"].startswith("account-test-")
    assert [(p["pillow_id"], p["role"]) for p in me["pillows"]] == [(TEST_PILLOW_ID, "owner")]

    again = client.post("/api/me/join-demo", headers=auth).json()
    assert again["contact_id"] == me["contact_id"] and len(again["pillows"]) == 1
    assert client.get(PREFS_URL, headers=auth).status_code == 200


@pytest.fixture
def real_pillow_id(db: Client, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """A throwaway id standing in for the real pillow; the pillow and resident it gets are removed."""
    pillow_id = f"test-new-{secrets.token_hex(4)}"
    monkeypatch.setattr(account_router, "REAL_PILLOW_ID", pillow_id)
    try:
        yield pillow_id
    finally:
        row = db.table(PILLOWS_TABLE).select("resident_id").eq("id", pillow_id).execute().data
        db.table(PILLOWS_TABLE).delete().eq("id", pillow_id).execute()
        if row:
            db.table(RESIDENTS_TABLE).delete().eq("id", row[0]["resident_id"]).execute()


def test_connect_creates_the_pillow_for_the_named_person(client: TestClient, db: Client, real_pillow_id: str):
    with _throwaway_login(db) as (user_id, token), _throwaway_login(db) as (other_id, other):
        try:
            auth = {"Authorization": f"Bearer {token}"}
            assert client.post("/api/me/pillows", json={"name": "  "}, headers=auth).status_code == 422

            me = client.post("/api/me/pillows", json={"name": " Halina "}, headers=auth).json()
            [pillow] = me["pillows"]
            assert (pillow["pillow_id"], pillow["role"], pillow["preferred_name"]) == (
                real_pillow_id,
                "owner",
                "Halina",
            )
            # Watched all day until the app narrows it (quiet_start == quiet_end)
            link = db.table(PILLOWS_TABLE).select("resident_id").eq("id", real_pillow_id).execute().data[0]
            hours = (
                db.table(RESIDENTS_TABLE)
                .select("quiet_start, quiet_end")
                .eq("id", link["resident_id"])
                .execute()
                .data[0]
            )
            assert hours["quiet_start"] == hours["quiet_end"]

            # The owner may send it again (a retry, or a changed name); anyone else is turned away
            again = client.post("/api/me/pillows", json={"name": "Babcia"}, headers=auth).json()
            assert [p["preferred_name"] for p in again["pillows"]] == ["Babcia"]
            taken = client.post(
                "/api/me/pillows", json={"name": "X"}, headers={"Authorization": f"Bearer {other}"}
            )
            assert taken.status_code == 409
        finally:
            db.table(CONTACTS_TABLE).delete().in_("user_id", [user_id, other_id]).execute()
