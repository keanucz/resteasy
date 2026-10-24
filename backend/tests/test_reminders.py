"""Reminders (the Routine agent): the planner offline, then the router against live Supabase."""

import time as clock
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from supabase import Client

from app.agents.guardian import Guardian
from app.agents.night_watch import Alert, Command, Event, NightWatch, NightWatchConfig, State
from app.agents.reminders import MAX_ASKS, RETRY_AFTER, next_step, result_status, slot_today, spoken_line
from app.core.config import get_settings
from app.crud.crud_constants import REMINDER_OCCURRENCES_TABLE, REMINDERS_TABLE
from app.schemas.reminder import ReminderCreate, ReminderUpdate
from tests.seed_constants import TEST_PILLOW_ID, TEST_RESIDENT_ID

TZ = "America/Los_Angeles"
SAT_8AM = datetime(2026, 10, 24, 8, 0, tzinfo=ZoneInfo(TZ))  # a Saturday (ISO 6)
EVERY_DAY = {"days": [1, 2, 3, 4, 5, 6, 7], "time_of_day": "08:00:00"}


def occ(status="waiting", attempts=0, asked=None, due=SAT_8AM):
    return {"status": status, "attempts": attempts, "due_at": due.isoformat(),
            "last_asked_at": asked.isoformat() if asked else None}


# ---------- schedule ----------

def test_slot_is_today_in_her_timezone_once_the_time_has_passed():
    assert slot_today(EVERY_DAY, TZ, SAT_8AM - timedelta(minutes=1)) is None
    assert slot_today(EVERY_DAY, TZ, SAT_8AM + timedelta(minutes=5)) == SAT_8AM
    # 08:05 in California is 15:05 UTC: the slot follows her clock, not the server's
    assert slot_today(EVERY_DAY, TZ, (SAT_8AM + timedelta(minutes=5)).astimezone(UTC)) == SAT_8AM


def test_slot_only_on_chosen_weekdays_and_not_hours_late():
    weekdays = {**EVERY_DAY, "days": [1, 2, 3, 4, 5]}
    assert slot_today(weekdays, TZ, SAT_8AM + timedelta(minutes=5)) is None
    assert slot_today(EVERY_DAY, TZ, SAT_8AM + timedelta(hours=3)) is None


# ---------- delivery ----------

@pytest.mark.parametrize("night_state", ["in_bed", "up", "check_in", "escalating"])
def test_never_wakes_her_or_talks_over_a_check_in(night_state):
    assert next_step(occ(), True, night_state, SAT_8AM + timedelta(minutes=1)) is None


def test_due_with_buzzer_once_she_is_up_for_the_day():
    now = SAT_8AM + timedelta(minutes=40)  # held while she slept in
    step = next_step(occ(), False, "awake", now)
    assert step.status == "due" and step.buzz
    assert step.fields == {"status": "due", "attempts": 1, "last_asked_at": now.isoformat()}


def test_confirm_retries_once_after_ten_minutes_then_missed():
    asked = SAT_8AM
    # she said "not yet" (or nothing): one more try, not before the retry delay
    assert result_status("not_done", 1, confirm=True) == "waiting"
    too_soon = asked + RETRY_AFTER - timedelta(seconds=1)
    assert next_step(occ("waiting", 1, asked), True, "awake", too_soon) is None
    step = next_step(occ("waiting", 1, asked), True, "awake", asked + RETRY_AFTER)
    assert step.status == "due" and step.fields["attempts"] == 2 == MAX_ASKS
    assert result_status("no_answer", MAX_ASKS, confirm=True) == "missed"


def test_announce_only_never_retries():
    assert result_status("announced", 1, confirm=False) == "announced"
    assert result_status("no_answer", 1, confirm=False) == "missed"


def test_a_laptop_that_never_reports_counts_as_no_answer():
    asked = SAT_8AM
    assert next_step(occ("due", 1, asked), True, "awake", asked + timedelta(minutes=5)) is None
    assert next_step(occ("due", 1, asked), True, "awake", asked + RETRY_AFTER).status == "waiting"
    assert next_step(occ("due", 1, asked), False, "awake", asked + RETRY_AFTER).status == "missed"


def test_still_open_three_hours_late_is_missed_even_while_held():
    assert next_step(occ(), True, "in_bed", SAT_8AM + timedelta(hours=3)).status == "missed"


def test_done_and_distress_close_it():
    assert result_status("done", 1, confirm=True) == "done"
    assert result_status("distress", 1, confirm=True) == "missed"  # family are alerted instead


def test_spoken_line():
    line = spoken_line("Margaret", "take your heart tablets")
    assert line == "Margaret, it's time to take your heart tablets."


# ---------- validation ----------

def test_label_is_an_action_phrase_and_days_are_iso_weekdays():
    r = ReminderCreate(label="  Take your heart tablets. ", time_of_day="08:00", days=[7, 1, 1])
    assert r.label == "Take your heart tablets" and r.days == [1, 7] and not r.confirm
    for bad in ({"days": []}, {"days": [0]}, {"days": [8]}, {"label": " . "}, {"label": "x" * 81}):
        with pytest.raises(ValidationError):
            ReminderCreate(**{"label": "walk the dog", "time_of_day": "16:00", **bad})
    assert ReminderUpdate(active=False).model_dump(exclude_none=True) == {"active": False}


def test_guardian_screens_the_buzzer():
    g = Guardian()
    assert g.check(Command("mum", "buzz", {"pattern": "chime", "repeat": 1}), clock.time()).allowed
    capped = g.check(Command("mum", "buzz", {"pattern": "chime", "repeat": 9}), clock.time())
    assert capped.replacement.args["repeat"] == 3
    assert not g.check(Command("mum", "buzz", {"pattern": "siren", "repeat": 1}), clock.time()).allowed


# ---------- distress outside a check-in ----------

def test_distress_heard_by_day_escalates_as_distress():
    nw = NightWatch(NightWatchConfig(contacts=("Sarah",)))
    out = nw.distress_heard(1_000.0, 'Asked about her reminder, she said: "I\'ve fallen"')
    assert nw.state is State.ESCALATING
    step = next(a for a in out if isinstance(a, Event) and a.type == "escalation_step")
    assert step.data["kind"] == "distress"
    alert = next(a for a in out if isinstance(a, Alert))
    assert alert.message.startswith("Mum may need help.") and "fallen" in alert.message
    assert nw.distress_heard(1_010.0, "again") == []  # an escalation already running goes on


# ---------- router (live Supabase; skipped without credentials) ----------

BASE = f"/api/pillows/{TEST_PILLOW_ID}/reminders"


@pytest.fixture
def reminders_client(db: Client, live_client: TestClient):
    """The live client, with the test resident's reminders removed afterwards."""
    yield live_client
    db.table(REMINDERS_TABLE).delete().eq("resident_id", TEST_RESIDENT_ID).execute()


def _due_occurrence(db: Client, reminder_id: int) -> int:
    now = datetime.now(UTC).isoformat()
    row = {"reminder_id": reminder_id, "due_at": now, "status": "due", "attempts": 1, "last_asked_at": now}
    return db.table(REMINDER_OCCURRENCES_TABLE).insert(row).execute().data[0]["id"]


def test_reminder_crud_round_trip(reminders_client: TestClient):
    made = reminders_client.post(BASE, json={"label": "walk the dog", "time_of_day": "16:00", "days": [6, 7]})
    assert made.status_code == 201
    rid = made.json()["id"]
    expected = {"label": "walk the dog", "kind": "custom", "time_of_day": "16:00:00", "days": [6, 7],
                "confirm": False, "active": True}
    assert made.json() == {"id": rid, **expected}
    assert [r["id"] for r in reminders_client.get(BASE).json()] == [rid]
    patched = reminders_client.patch(f"{BASE}/{rid}", json={"confirm": True, "active": False}).json()
    assert patched["confirm"] and not patched["active"]
    assert reminders_client.delete(f"{BASE}/{rid}").status_code == 204
    assert reminders_client.delete(f"{BASE}/{rid}").status_code == 404


def test_medical_claim_in_a_label_is_rejected(reminders_client: TestClient):
    label = "check for symptoms of a stroke"
    response = reminders_client.post(BASE, json={"label": label, "time_of_day": "09:00"})
    assert response.status_code == 422


def test_another_residents_reminder_is_404(db: Client, reminders_client: TestClient):
    olive = {"full_name": "Other Test", "preferred_name": "Olive"}
    other = db.table("residents").insert(olive).execute().data[0]
    try:
        theirs = db.table(REMINDERS_TABLE).insert({"resident_id": other["id"], "label": "x",
                                                   "time_of_day": "09:00"}).execute().data[0]
        assert reminders_client.patch(f"{BASE}/{theirs['id']}", json={"active": False}).status_code == 404
        assert reminders_client.delete(f"{BASE}/{theirs['id']}").status_code == 404
    finally:
        db.table("residents").delete().eq("id", other["id"]).execute()


def test_occurrence_is_claimed_once(db: Client, reminders_client: TestClient):
    rid = reminders_client.post(BASE, json={"label": "call Sarah", "time_of_day": "10:00"}).json()["id"]
    row = {"reminder_id": rid, "due_at": "2026-10-24T17:00:00+00:00"}
    for _ in range(2):
        db.table(REMINDER_OCCURRENCES_TABLE).upsert(row, on_conflict="reminder_id,due_at",
                                                    ignore_duplicates=True).execute()
    assert len(db.table(REMINDER_OCCURRENCES_TABLE).select("id").eq("reminder_id", rid).execute().data) == 1


def test_due_list_and_confirmed_result(db: Client, reminders_client: TestClient):
    token = get_settings().checkin_token
    if not token:
        pytest.skip("CHECKIN_TOKEN not set")
    rid = reminders_client.post(BASE, json={"label": "take your heart tablets", "kind": "meds",
                                            "time_of_day": "08:00", "confirm": True}).json()["id"]
    oid = _due_occurrence(db, rid)
    assert reminders_client.get(f"{BASE}/due").json() == [
        {"occurrence_id": oid, "text": "Tess, it's time to take your heart tablets.", "confirm": True}]
    url = f"{BASE}/{oid}/result"
    assert reminders_client.post(url, json={"outcome": "done"}).status_code == 401
    auth = {"Authorization": f"Bearer {token}"}
    done = reminders_client.post(url, json={"outcome": "done", "reply": "yes, with breakfast"}, headers=auth)
    assert done.json() == {"status": "done"}
    again = reminders_client.post(url, json={"outcome": "no_answer"}, headers=auth)
    assert again.json() == {"status": "done"}  # a repeated report changes nothing
    assert reminders_client.get(f"{BASE}/due").json() == []
    today = reminders_client.get(f"{BASE}/today").json()
    assert [(o["id"], o["status"], o["reply"]) for o in today] == [(oid, "done", "yes, with breakfast")]
