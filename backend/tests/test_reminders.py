"""Reminders (the Routine agent): the planner offline, then the router against live Supabase.

The live tests only touch the test resident (the owner of `test-pillow`), never `mum` or `demo-dad`.
"""

import time as clock
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from supabase import Client

from app.agents.guardian import Guardian
from app.agents.night_watch import Alert, Command, Event, NightWatch, NightWatchConfig, State
from app.agents.reminders import (
    AGENT,
    MAX_ASKS,
    RETRY_AFTER,
    next_step,
    result_status,
    slot_today,
    spoken_line,
)
from app.core.app_constants import (
    AGENT_CONTACT_MISSING,
    AGENT_CONTACT_NOT_LINKED,
    FAMILY_AGENT,
    PILLOW_VOICE_AGENT,
)
from app.core.config import get_settings
from app.crud.crud_constants import (
    AGENT_LOG_TABLE,
    OCCURRENCE_KEY,
    REMINDER_OCCURRENCES_TABLE,
    REMINDERS_TABLE,
    RESIDENTS_TABLE,
)
from app.schemas.reminder import ReminderCreate, ReminderUpdate
from tests.seed_constants import TEST_PILLOW_ID, TEST_RESIDENT_ID, TEST_USER_ID, UNKNOWN_CONTACT_ID

TZ = "America/Los_Angeles"
SAT_8AM = datetime(2026, 10, 24, 8, 0, tzinfo=ZoneInfo(TZ))  # a Saturday (ISO 6)
EVERY_DAY = {
    "days": [1, 2, 3, 4, 5, 6, 7],
    "time_of_day": "08:00:00",
    "on_date": None,
    "skip_dates": [],
    "active": True,
    "consent": "agreed",
    "consent_at": None,
}


def occ(status="waiting", attempts=0, asked=None, due=SAT_8AM):
    return {
        "purpose": "remind",
        "status": status,
        "attempts": attempts,
        "due_at": due.isoformat(),
        "last_asked_at": asked.isoformat() if asked else None,
    }


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


# ---------- router: login (offline) ----------

BASE = f"/api/pillows/{TEST_PILLOW_ID}/reminders"
CALENDAR = f"{BASE}/calendar?start=2026-11-01&end=2026-11-07"
NEW = {"label": "walk the dog", "time_of_day": "16:00", "days": [6, 7]}


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer not-a-real-token"}])
def test_changing_reminders_and_the_calendar_need_a_login(offline_client: TestClient, headers):
    assert offline_client.post(BASE, json=NEW, headers=headers).status_code == 401
    assert offline_client.patch(f"{BASE}/1", json={"active": False}, headers=headers).status_code == 401
    assert offline_client.delete(f"{BASE}/1", headers=headers).status_code == 401
    assert offline_client.get(CALENDAR, headers=headers).status_code == 401


@pytest.fixture
def checkin_auth() -> dict[str, str]:
    token = get_settings().checkin_token
    if not token:
        pytest.skip("CHECKIN_TOKEN not set")
    return _bearer(token)


def test_the_agent_token_must_name_a_contact(offline_client: TestClient, checkin_auth: dict):
    calls = [
        offline_client.post(BASE, json=NEW, headers=checkin_auth),
        offline_client.patch(f"{BASE}/1", json={"active": False}, headers=checkin_auth),
        offline_client.delete(f"{BASE}/1", headers=checkin_auth),
    ]
    assert [(r.status_code, r.json()["detail"]) for r in calls] == [(422, AGENT_CONTACT_MISSING)] * 3


# ---------- router (live Supabase; skipped without credentials) ----------


@pytest.fixture
def reminders_client(db: Client, live_client: TestClient):
    """The live client, with the test resident's reminders and the Routine and family agents' log
    rows on the test pillow removed afterwards (from a minute early: this clock may run ahead of
    the database's)."""
    started = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    yield live_client
    db.table(REMINDERS_TABLE).delete().eq("resident_id", TEST_RESIDENT_ID).execute()
    db.table(AGENT_LOG_TABLE).delete().eq("pillow_id", TEST_PILLOW_ID).in_(
        "agent", [AGENT, FAMILY_AGENT, PILLOW_VOICE_AGENT]
    ).gte("ts", started).execute()


def _family_agent_log(db: Client, reminder_id: int) -> list[dict]:
    """What the family agent logged about this reminder on the test pillow, oldest first."""
    return (
        db.table(AGENT_LOG_TABLE)
        .select("intent, tool, args")
        .eq("pillow_id", TEST_PILLOW_ID)
        .eq("agent", FAMILY_AGENT)
        .eq("args->>reminder_id", str(reminder_id))
        .order("id")
        .execute()
        .data
    )


def _due_occurrence(db: Client, reminder_id: int, purpose: str = "remind") -> int:
    now = datetime.now(UTC).isoformat()
    row = {
        "reminder_id": reminder_id,
        "due_at": now,
        "status": "due",
        "attempts": 1,
        "last_asked_at": now,
        "purpose": purpose,
    }
    return db.table(REMINDER_OCCURRENCES_TABLE).insert(row).execute().data[0]["id"]


def _reminder(db: Client, reminder_id: int) -> dict:
    return db.table(REMINDERS_TABLE).select("*").eq("id", reminder_id).single().execute().data


def _due(client: TestClient, oid: int) -> list[dict]:
    """GET /due, only this occurrence (the API's own ticker may add others for the test pillow)."""
    return [d for d in client.get(f"{BASE}/due").json() if d["occurrence_id"] == oid]


def test_reminder_crud_round_trip(reminders_client: TestClient, owner_token: str):
    auth = _bearer(owner_token)
    made = reminders_client.post(BASE, json=NEW, headers=auth)
    assert made.status_code == 201
    rid = made.json()["id"]
    expected = {
        "label": "walk the dog",
        "kind": "custom",
        "time_of_day": "16:00",
        "days": [6, 7],
        "on_date": None,
        "skip_dates": [],
        "channels": ["voice"],
        "confirm": False,
        "active": True,
        "consent": "pending",
        "consent_at": None,
        "created_by_name": "Test User",
    }
    assert made.json() == {"id": rid, **expected}
    assert reminders_client.get(BASE).json() == [made.json()]
    patched = reminders_client.patch(f"{BASE}/{rid}", json={"confirm": True, "active": False}, headers=auth)
    assert patched.json()["confirm"] and not patched.json()["active"]
    assert reminders_client.delete(f"{BASE}/{rid}", headers=auth).status_code == 204
    assert reminders_client.delete(f"{BASE}/{rid}", headers=auth).status_code == 404


def test_a_contact_sets_one_up_too_and_a_stranger_cannot(
    reminders_client: TestClient, contact_token: str, stranger_token: str
):
    made = reminders_client.post(BASE, json=NEW, headers=_bearer(contact_token))
    assert made.status_code == 201 and made.json()["created_by_name"] == "Test Helper"
    stranger = _bearer(stranger_token)
    assert reminders_client.post(BASE, json=NEW, headers=stranger).status_code == 403
    assert (
        reminders_client.patch(
            f"{BASE}/{made.json()['id']}", json={"active": False}, headers=stranger
        ).status_code
        == 403
    )
    assert reminders_client.get(CALENDAR, headers=stranger).status_code == 403


def test_medical_claim_in_a_label_is_rejected(reminders_client: TestClient, owner_token: str):
    label = "check for symptoms of a stroke"
    response = reminders_client.post(
        BASE, json={"label": label, "time_of_day": "09:00"}, headers=_bearer(owner_token)
    )
    assert response.status_code == 422


def test_another_residents_reminder_is_404(db: Client, reminders_client: TestClient, owner_token: str):
    olive = {"full_name": "Other Test", "preferred_name": "Olive"}
    other = db.table("residents").insert(olive).execute().data[0]
    auth = _bearer(owner_token)
    try:
        theirs = (
            db.table(REMINDERS_TABLE)
            .insert({"resident_id": other["id"], "label": "x", "time_of_day": "09:00"})
            .execute()
            .data[0]
        )
        assert (
            reminders_client.patch(f"{BASE}/{theirs['id']}", json={"active": False}, headers=auth).status_code
            == 404
        )
        assert reminders_client.delete(f"{BASE}/{theirs['id']}", headers=auth).status_code == 404
    finally:
        db.table("residents").delete().eq("id", other["id"]).execute()


def test_occurrence_is_claimed_once(db: Client, reminders_client: TestClient, owner_token: str):
    rid = reminders_client.post(
        BASE, json={"label": "call Sarah", "time_of_day": "10:00"}, headers=_bearer(owner_token)
    ).json()["id"]
    row = {"reminder_id": rid, "due_at": "2026-10-24T17:00:00+00:00", "purpose": "remind"}
    for _ in range(2):
        db.table(REMINDER_OCCURRENCES_TABLE).upsert(
            row, on_conflict=OCCURRENCE_KEY, ignore_duplicates=True
        ).execute()
    assert len(db.table(REMINDER_OCCURRENCES_TABLE).select("id").eq("reminder_id", rid).execute().data) == 1


def test_changing_when_asks_her_again_but_skipping_a_day_does_not(
    db: Client, reminders_client: TestClient, owner_token: str
):
    auth = _bearer(owner_token)
    rid = reminders_client.post(BASE, json=NEW, headers=auth).json()["id"]
    agreed_at = "2026-10-25T17:00:00+00:00"
    db.table(REMINDERS_TABLE).update({"consent": "agreed", "consent_at": agreed_at}).eq("id", rid).execute()
    skipped = reminders_client.patch(
        f"{BASE}/{rid}", json={"skip_dates": ["2026-11-07"]}, headers=auth
    ).json()
    assert skipped["skip_dates"] == ["2026-11-07"] and skipped["consent"] == "agreed"
    moved = reminders_client.patch(f"{BASE}/{rid}", json={"time_of_day": "17:15"}, headers=auth).json()
    assert (moved["time_of_day"], moved["consent"], moved["consent_at"]) == ("17:15", "pending", None)


def test_calendar_lays_out_one_offs_and_weekdays_minus_skipped_dates(
    db: Client, reminders_client: TestClient, owner_token: str
):
    auth = _bearer(owner_token)
    tz = ZoneInfo(
        db.table(RESIDENTS_TABLE)
        .select("timezone")
        .eq("id", TEST_RESIDENT_ID)
        .single()
        .execute()
        .data["timezone"]
    )
    once = reminders_client.post(
        BASE,
        json={"label": "call Sarah", "kind": "call", "time_of_day": "15:00", "on_date": "2026-11-01"},
        headers=auth,
    ).json()
    weekdays = reminders_client.post(
        BASE,
        json={
            "label": "take your heart tablets",
            "kind": "meds",
            "time_of_day": "08:30",
            "days": [1, 2, 3, 4, 5],
            "confirm": True,
        },
        headers=auth,
    ).json()
    reminders_client.patch(f"{BASE}/{weekdays['id']}", json={"skip_dates": ["2026-11-03"]}, headers=auth)
    paused = reminders_client.post(BASE, json=NEW, headers=auth).json()
    reminders_client.patch(f"{BASE}/{paused['id']}", json={"active": False}, headers=auth)
    monday = datetime(2026, 11, 2, 8, 30, tzinfo=tz)
    db.table(REMINDER_OCCURRENCES_TABLE).insert(
        {"reminder_id": weekdays["id"], "due_at": monday.isoformat(), "status": "done", "purpose": "remind"}
    ).execute()

    response = reminders_client.get(CALENDAR, headers=auth)
    assert response.status_code == 200
    entries = response.json()
    got = [
        (e["reminder_id"], e["date"], datetime.fromisoformat(e["due_at"]), e["recurring"], e["status"])
        for e in entries
    ]
    plays = [(once["id"], date(2026, 11, 1), 15, False)] + [
        (weekdays["id"], date(2026, 11, d), 8, True) for d in (2, 4, 5, 6)
    ]
    assert got == [
        (
            rid,
            day.isoformat(),
            datetime(day.year, day.month, day.day, hour, 30 if recurring else 0, tzinfo=tz),
            recurring,
            "done" if day.day == 2 else None,
        )
        for rid, day, hour, recurring in plays
    ]
    assert entries[0] == {
        "reminder_id": once["id"],
        "date": "2026-11-01",
        "due_at": entries[0]["due_at"],
        "label": "call Sarah",
        "kind": "call",
        "confirm": False,
        "consent": "pending",
        "recurring": False,
        "status": None,
    }
    assert datetime.fromisoformat(entries[0]["due_at"]).utcoffset() is not None  # an offset, never naive


@pytest.mark.parametrize(
    "query",
    [
        "start=2026-11-07&end=2026-11-01",
        "start=2026-11-01&end=2027-01-02",
        "start=2026-11-01",
        "start=soon&end=2026-11-02",
    ],
)
def test_calendar_range_is_checked(reminders_client: TestClient, owner_token: str, query: str):
    assert reminders_client.get(f"{BASE}/calendar?{query}", headers=_bearer(owner_token)).status_code == 422


def test_she_agrees_through_the_pillow(
    db: Client, reminders_client: TestClient, owner_token: str, checkin_auth: dict
):
    made = reminders_client.post(
        BASE,
        json={"label": "take your heart tablets", "kind": "meds", "time_of_day": "08:00", "confirm": True},
        headers=_bearer(owner_token),
    ).json()
    oid = _due_occurrence(db, made["id"], purpose="consent")
    assert _due(reminders_client, oid) == [
        {
            "occurrence_id": oid,
            "confirm": True,
            "purpose": "consent",
            "text": "Test would like to remind you to take your heart tablets at 8 am every day. "
            "Is that alright?",
        }
    ]
    url = f"{BASE}/{oid}/result"
    assert reminders_client.post(url, json={"outcome": "done"}).status_code == 401
    silent = reminders_client.post(url, json={"outcome": "no_answer"}, headers=checkin_auth)
    assert silent.json() == {"status": "waiting"} and _reminder(db, made["id"])["consent"] == "pending"
    db.table(REMINDER_OCCURRENCES_TABLE).update({"status": "due", "attempts": 2}).eq("id", oid).execute()
    yes = reminders_client.post(url, json={"outcome": "done", "reply": "yes please"}, headers=checkin_auth)
    assert yes.json() == {"status": "done"}
    stored = _reminder(db, made["id"])
    assert stored["consent"] == "agreed" and stored["consent_at"] is not None
    assert reminders_client.get(BASE).json()[0]["consent"] == "agreed"
    assert oid not in [o["id"] for o in reminders_client.get(f"{BASE}/today").json()]  # not a reminder
    logged = (
        db.table(AGENT_LOG_TABLE)
        .select("intent")
        .eq("pillow_id", TEST_PILLOW_ID)
        .eq("agent", AGENT)
        .order("ts", desc=True)
        .limit(1)
        .execute()
        .data
    )
    assert logged == [{"intent": "she agreed to a new reminder: take your heart tablets"}]


def test_she_declines_through_the_pillow(
    db: Client, reminders_client: TestClient, owner_token: str, checkin_auth: dict
):
    made = reminders_client.post(
        BASE,
        json={"label": "call Ella", "kind": "call", "time_of_day": "18:30", "days": [1, 2, 3, 4, 5]},
        headers=_bearer(owner_token),
    ).json()
    oid = _due_occurrence(db, made["id"], purpose="consent")
    assert _due(reminders_client, oid)[0]["text"] == (
        "Test would like to remind you to call Ella at 6:30 pm on weekdays. Is that alright?"
    )
    no = reminders_client.post(
        f"{BASE}/{oid}/result", json={"outcome": "not_done", "reply": "no thank you"}, headers=checkin_auth
    )
    assert no.json() == {"status": "done"}
    assert _reminder(db, made["id"])["consent"] == "declined"


def test_due_list_and_confirmed_result(
    db: Client, reminders_client: TestClient, owner_token: str, checkin_auth: dict
):
    rid = reminders_client.post(
        BASE,
        json={"label": "take your heart tablets", "kind": "meds", "time_of_day": "08:00", "confirm": True},
        headers=_bearer(owner_token),
    ).json()["id"]
    oid = _due_occurrence(db, rid)
    assert _due(reminders_client, oid) == [
        {
            "occurrence_id": oid,
            "text": "Tess, it's time to take your heart tablets.",
            "confirm": True,
            "purpose": "remind",
        }
    ]
    url = f"{BASE}/{oid}/result"
    assert reminders_client.post(url, json={"outcome": "done"}).status_code == 401
    done = reminders_client.post(
        url, json={"outcome": "done", "reply": "yes, with breakfast"}, headers=checkin_auth
    )
    assert done.json() == {"status": "done"}
    again = reminders_client.post(url, json={"outcome": "no_answer"}, headers=checkin_auth)
    assert again.json() == {"status": "done"}  # a repeated report changes nothing
    assert _due(reminders_client, oid) == []
    today = reminders_client.get(f"{BASE}/today").json()
    assert [(o["id"], o["status"], o["reply"], o["purpose"]) for o in today if o["id"] == oid] == [
        (oid, "done", "yes, with breakfast", "remind")
    ]


# ---------- the Fetch.ai family agent, with the agent token (live) ----------


def test_family_agent_sets_up_changes_and_deletes_for_a_contact(
    db: Client, reminders_client: TestClient, checkin_auth: dict
):
    for_owner = f"?contact_id={TEST_USER_ID}"
    made = reminders_client.post(f"{BASE}{for_owner}", json=NEW, headers=checkin_auth)
    assert made.status_code == 201
    assert (made.json()["created_by_name"], made.json()["consent"]) == ("Test User", "pending")
    rid = made.json()["id"]
    assert _reminder(db, rid)["created_by"] == TEST_USER_ID
    db.table(REMINDERS_TABLE).update({"consent": "agreed"}).eq("id", rid).execute()
    url = f"{BASE}/{rid}{for_owner}"
    paused = reminders_client.patch(url, json={"active": False}, headers=checkin_auth).json()
    assert (paused["active"], paused["consent"]) == (False, "agreed")
    assert reminders_client.patch(url, json={"active": False}, headers=checkin_auth).status_code == 200
    moved = reminders_client.patch(url, json={"time_of_day": "17:15"}, headers=checkin_auth).json()
    assert (moved["time_of_day"], moved["consent"]) == ("17:15", "pending")  # she is asked again
    assert reminders_client.delete(url, headers=checkin_auth).status_code == 204
    assert reminders_client.delete(url, headers=checkin_auth).status_code == 404

    logged = _family_agent_log(db, rid)  # the repeated pause wrote nothing, so logged nothing
    assert [row["intent"] for row in logged] == [
        "set up a reminder for Test User: walk the dog",
        "changed a reminder for Test User: walk the dog",
        "changed a reminder for Test User: walk the dog",
        "deleted a reminder for Test User: walk the dog",
    ]
    assert {row["tool"] for row in logged} == {"reminders"}
    assert all(row["args"]["contact_id"] == TEST_USER_ID for row in logged)
    assert logged[2]["args"]["fields"] == {"time_of_day": "17:15", "consent": "pending", "consent_at": None}


def test_family_agent_only_acts_for_her_contacts_and_labels_are_screened(
    reminders_client: TestClient, owner_token: str, checkin_auth: dict
):
    rid = reminders_client.post(BASE, json=NEW, headers=_bearer(owner_token)).json()["id"]
    stranger = f"?contact_id={UNKNOWN_CONTACT_ID}"
    calls = [
        reminders_client.post(f"{BASE}{stranger}", json=NEW, headers=checkin_auth),
        reminders_client.patch(f"{BASE}/{rid}{stranger}", json={"active": False}, headers=checkin_auth),
        reminders_client.delete(f"{BASE}/{rid}{stranger}", headers=checkin_auth),
    ]
    assert [(r.status_code, r.json()["detail"]) for r in calls] == [(403, AGENT_CONTACT_NOT_LINKED)] * 3
    not_a_uuid = reminders_client.post(f"{BASE}?contact_id=sarah", json=NEW, headers=checkin_auth)
    assert not_a_uuid.status_code == 422
    medical = {"label": "check for symptoms of a stroke", "time_of_day": "09:00"}
    response = reminders_client.post(f"{BASE}?contact_id={TEST_USER_ID}", json=medical, headers=checkin_auth)
    assert response.status_code == 422
    assert reminders_client.get(BASE).json()[0]["active"]  # the stranger changed nothing


def test_she_sets_a_reminder_by_voice_and_her_yes_is_her_consent(
    reminders_client: TestClient, db: Client, checkin_auth: dict
):
    """The base laptop, for her (the talk key): `as=resident`, no contact. Agreed at once, logged."""
    tablets = {"label": "take your tablets", "time_of_day": "08:00", "on_date": "2026-11-02", "kind": "meds"}
    made = reminders_client.post(f"{BASE}?as=resident", json=tablets, headers=checkin_auth)
    assert made.status_code == 201
    stored = db.table(REMINDERS_TABLE).select("consent, created_by").eq("id", made.json()["id"])
    assert stored.single().execute().data == {"consent": "agreed", "created_by": None}
    log = db.table(AGENT_LOG_TABLE).select("intent").eq("pillow_id", TEST_PILLOW_ID)
    intents = [r["intent"] for r in log.eq("agent", PILLOW_VOICE_AGENT).execute().data]
    assert any("by voice: take your tablets" in i for i in intents)
    one_day = f"{BASE}/calendar?as=resident&start=2026-11-02&end=2026-11-02"
    days = reminders_client.get(one_day, headers=checkin_auth)
    assert [e["label"] for e in days.json()] == ["take your tablets"]
    dose = dict(tablets, label="take double your dose")
    assert reminders_client.post(f"{BASE}?as=resident", json=dose, headers=checkin_auth).status_code == 422


def test_as_resident_needs_the_agent_token(offline_client: TestClient):
    response = offline_client.post(f"{BASE}?as=resident", json=NEW, headers=_bearer("not-a-real-token"))
    assert response.status_code == 401
