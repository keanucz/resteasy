"""Account API: the app's own login, offline checks, then a round trip against live Supabase."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.voice_constants import DEFAULT_VOICE_ID, VOICE_IDS
from app.schemas.account import PreferencesPatch
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
