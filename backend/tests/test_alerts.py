"""Settings > Alerts (/api/me/alerts): phone numbers, the keep-one rule and the test send offline,
then a round trip on the test user's own contact against live Supabase."""

import re
from collections.abc import Iterator
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from supabase import Client

from app.agents.reminders import slot_today
from app.core.app_constants import ALERT_DEBUG_NOT_TEST, KEEP_ONE_CHANNEL, LAST_ON_CALL, PHONE_INVALID
from app.core.dependencies import get_notifier
from app.crud.crud_constants import CONTACTS_TABLE, REMINDERS_TABLE
from app.main import app
from app.notify.sender import NotificationSender
from app.routers import alerts as alerts_router
from app.schemas.account import AlertSettingsPatch
from tests.seed_constants import TEST_PILLOW_ID, TEST_RESIDENT_ID, TEST_USER_ID
from tests.test_notify import FakeIMessage, FakeTwilio

URL = "/api/me/alerts"
ALERT_COLUMNS = (
    "phone",
    "sms_consent",
    "call_alerts",
    "app_alerts",
    "restless_alerts",
    "on_call",
    "quiet_start",
    "quiet_end",
    "is_test",
)


# ---------- offline ----------


@pytest.mark.parametrize(
    ("typed", "stored"),
    [
        ("+44 7700 900123", "+447700900123"),
        ("447700900123", "+447700900123"),
        ("0044 (7700) 900-123", "+447700900123"),
        ("", None),
    ],
)
def test_phone_numbers_are_stored_in_e164(typed, stored):
    assert AlertSettingsPatch(phone=typed).phone == stored


@pytest.mark.parametrize("typed", ["07700900123", "+44 77", "call me"])
def test_numbers_without_a_country_code_are_refused(typed):
    with pytest.raises(ValidationError, match=re.escape(PHONE_INVALID)):
        AlertSettingsPatch(phone=typed)


def test_the_patch_only_names_the_columns_it_was_sent():
    assert AlertSettingsPatch(sms=False, app=True).columns() == {"sms_consent": False, "app_alerts": True}
    assert AlertSettingsPatch(phone="").columns() == {"phone": None}


def test_alert_routes_need_a_valid_login(offline_client: TestClient):
    assert offline_client.get(URL).status_code == 401
    assert offline_client.post(f"{URL}/test", json={"channel": "sms"}).status_code == 401


# ---------- live Supabase (the test user's own contact) ----------


@pytest.fixture
def twilio() -> Iterator[FakeTwilio]:
    """A fake Twilio behind the app's notifier, and no test sent recently."""
    fake = FakeTwilio()
    app.dependency_overrides[get_notifier] = lambda: NotificationSender(FakeIMessage(fail="off"), fake, [])
    alerts_router._last_test.clear()
    yield fake
    alerts_router._last_test.clear()


@pytest.fixture
def auth(db: Client, owner_token: str) -> Iterator[dict[str, str]]:
    """The test user's login, with their phone and alert switches put back afterwards."""
    columns = ", ".join(ALERT_COLUMNS)
    saved = db.table(CONTACTS_TABLE).select(columns).eq("id", TEST_USER_ID).single().execute()
    try:
        yield {"Authorization": f"Bearer {owner_token}"}
    finally:
        db.table(CONTACTS_TABLE).update(saved.data).eq("id", TEST_USER_ID).execute()


def test_switches_and_number_round_trip(client: TestClient, auth, twilio):
    changed = client.patch(URL, json={"phone": "+1 555 555 0177", "call": False}, headers=auth)
    assert changed.status_code == 200
    assert {"phone": "+15555550177", "call": False, "twilio_ready": True}.items() <= changed.json().items()
    assert client.get(URL, headers=auth).json() == changed.json()


def test_one_way_to_reach_you_always_stays_on(client: TestClient, auth, twilio):
    refused = client.patch(URL, json={"app": False, "sms": False, "call": False}, headers=auth)
    assert (refused.status_code, refused.json()["detail"]) == (422, KEEP_ONE_CHANNEL)
    assert client.get(URL, headers=auth).json()["app"] is True


def test_another_contacts_number_is_refused(client: TestClient, db: Client, auth, twilio, contact_token):
    helper = db.table(CONTACTS_TABLE).select("id").eq("full_name", "Test Helper").limit(1).execute().data[0]
    db.table(CONTACTS_TABLE).update({"phone": "+15555550188"}).eq("id", helper["id"]).execute()
    assert client.patch(URL, json={"phone": "+15555550188"}, headers=auth).status_code == 409


def test_a_test_text_goes_to_your_own_number_once(client: TestClient, auth, twilio):
    client.patch(URL, json={"phone": "+15555550177", "sms": False}, headers=auth)
    sent = client.post(f"{URL}/test", json={"channel": "sms"}, headers=auth)
    assert sent.json() == {"sent": True, "via": "sms", "error": "iMessage off"}
    assert twilio.texts == [("+15555550177", twilio.texts[0][1])]
    assert client.post(f"{URL}/test", json={"channel": "sms"}, headers=auth).status_code == 429
    assert client.post(f"{URL}/test", json={"channel": "call"}, headers=auth).json()["via"] == "call"


def test_restless_notices_and_quiet_hours_round_trip(client: TestClient, auth, twilio):
    quiet = {"restless": False, "quiet_start": "22:00", "quiet_end": "07:00"}
    changed = client.patch(URL, json=quiet, headers=auth)
    assert quiet.items() <= changed.json().items()
    cleared = client.patch(URL, json={"quiet_start": None, "quiet_end": None}, headers=auth).json()
    assert (cleared["quiet_start"], cleared["quiet_end"]) == (None, None)


def test_the_last_contact_on_call_stays_on_call(client: TestClient, auth, twilio):
    # Test User is test-pillow's only contact
    refused = client.patch(URL, json={"on_call": False}, headers=auth)
    assert (refused.status_code, refused.json()["detail"]) == (422, LAST_ON_CALL)


def test_only_test_accounts_start_a_debug_alert(client: TestClient, db: Client, auth, twilio):
    debug = f"/api/pillows/{TEST_PILLOW_ID}/alert-debug"
    refused = client.post(f"{debug}/start", headers=auth)
    assert (refused.status_code, refused.json()["detail"]) == (403, ALERT_DEBUG_NOT_TEST)
    db.table(CONTACTS_TABLE).update({"is_test": True}).eq("id", TEST_USER_ID).execute()
    assert client.post(f"{debug}/start", headers=auth).json()["night_state"] == "escalating"
    assert client.post(f"{debug}/stop", headers=auth).json()["night_state"] != "escalating"


def test_a_debug_reminder_plays_on_the_next_tick(client: TestClient, db: Client, auth, twilio):
    url = f"/api/pillows/{TEST_PILLOW_ID}/alert-debug/reminder"
    refused = client.post(url, headers=auth)
    assert (refused.status_code, refused.json()["detail"]) == (403, ALERT_DEBUG_NOT_TEST)
    db.table(CONTACTS_TABLE).update({"is_test": True}).eq("id", TEST_USER_ID).execute()
    try:
        made = client.post(url, headers=auth)
        assert made.status_code == 200 and made.json()["night_state"]
        row = db.table(REMINDERS_TABLE).select("*").eq("resident_id", TEST_RESIDENT_ID).single().execute()
        resident = db.table("residents").select("timezone").eq("id", TEST_RESIDENT_ID).single().execute()
        row, tz = row.data, resident.data["timezone"]
        assert (row["consent"], row["confirm"]) == ("agreed", False)
        assert slot_today(row, tz, datetime.now(ZoneInfo(tz))) is not None  # due now, so the tick claims it
    finally:
        db.table(REMINDERS_TABLE).delete().eq("resident_id", TEST_RESIDENT_ID).execute()
