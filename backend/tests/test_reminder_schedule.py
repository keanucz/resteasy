"""Reminder schedule, consent and calendar logic, offline: pure functions over `reminders` rows."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.agents.reminder_schedule import consent_line, expand, first_name, plays_on, spoken_when
from app.agents.reminders import (
    MAX_ASKS,
    calendar_entries,
    consent_result,
    consent_slot_today,
    due_reminder,
    next_step,
    slot_today,
)
from app.core.app_constants import CALENDAR_MAX_DAYS, CONSENT_ASK_WINDOW, CONSENT_RETRY_AFTER
from app.schemas.reminder import CalendarRange, Reminder, ReminderCreate, ReminderUpdate

TZ = "America/Los_Angeles"
SUN_NOV_1 = date(2026, 11, 1)  # US clocks go back at 02:00 that morning
WEEK = [SUN_NOV_1 + timedelta(days=n) for n in range(7)]  # Sunday 1 to Saturday 7 November


def reminder(**changes) -> dict:
    """A reminders row as Supabase returns it: every day at 08:00, agreed."""
    row = {
        "id": 1,
        "label": "take your heart tablets",
        "kind": "meds",
        "time_of_day": "08:00:00",
        "days": [1, 2, 3, 4, 5, 6, 7],
        "on_date": None,
        "skip_dates": [],
        "channels": ["voice"],
        "confirm": True,
        "active": True,
        "consent": "agreed",
        "consent_at": None,
        "creator": None,
    }
    return {**row, **changes}


def at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=ZoneInfo(TZ))


# ---------- when it plays ----------


def test_recurring_plays_on_its_weekdays_except_skipped_dates():
    weekdays = reminder(days=[1, 2, 3, 4, 5], skip_dates=["2026-11-03"])
    assert [d for d in WEEK if plays_on(weekdays, d)] == [WEEK[1], WEEK[3], WEEK[4], WEEK[5]]


def test_one_off_plays_only_on_its_date_whatever_the_days():
    once = reminder(on_date="2026-11-07", days=[1])
    assert [d for d in WEEK if plays_on(once, d)] == [WEEK[6]]


def test_paused_never_plays_and_the_tick_waits_for_her_consent():
    assert not plays_on(reminder(active=False), SUN_NOV_1)
    for consent in ("pending", "declined"):
        assert plays_on(reminder(consent=consent), SUN_NOV_1)  # the calendar still shows it
        assert not plays_on(reminder(consent=consent), SUN_NOV_1, agreed_only=True)
    assert plays_on(reminder(), SUN_NOV_1, agreed_only=True)


def test_expand_gives_local_due_times_across_the_clock_change():
    out = expand(reminder(days=[7, 1]), SUN_NOV_1, WEEK[-1], TZ)
    assert out == [(SUN_NOV_1, at(SUN_NOV_1, 8)), (WEEK[1], at(WEEK[1], 8))]
    assert out[0][1].utcoffset() == timedelta(hours=-8)  # PST from that morning
    assert expand(reminder(on_date="2026-12-25"), SUN_NOV_1, WEEK[-1], TZ) == []


def test_slot_today_uses_plays_on_and_starts_after_she_agreed():
    now = at(WEEK[2], 8, 5)  # Tuesday 08:05
    assert slot_today(reminder(), TZ, now) == at(WEEK[2], 8)
    assert slot_today(reminder(skip_dates=["2026-11-03"]), TZ, now) is None
    assert slot_today(reminder(consent="pending"), TZ, now) is None
    assert slot_today(reminder(on_date="2026-11-03"), TZ, now) == at(WEEK[2], 8)
    agreed_late = reminder(consent_at=at(WEEK[2], 8, 2).isoformat())
    assert slot_today(agreed_late, TZ, now) is None  # she said yes after 08:00: tomorrow it plays


# ---------- how the pillow asks ----------


@pytest.mark.parametrize(
    ("changes", "when"),
    [
        ({}, "at 8 am every day"),
        ({"time_of_day": "18:30:00", "days": [1, 2, 3, 4, 5]}, "at 6:30 pm on weekdays"),
        ({"time_of_day": "15:00", "on_date": "2026-11-01"}, "at 3 pm on Sunday 1 November"),
        ({"time_of_day": "12:00", "days": [6, 7]}, "at 12 pm on weekends"),
        ({"time_of_day": "00:15", "days": [1, 4]}, "at 12:15 am on Mondays and Thursdays"),
        ({"days": [1, 3, 5]}, "at 8 am on Mondays, Wednesdays and Fridays"),
        ({"days": [6]}, "at 8 am on Saturdays"),
    ],
)
def test_spoken_when(changes, when):
    assert spoken_when(reminder(**changes)) == when


def test_consent_line_names_who_set_it_up():
    line = consent_line(reminder(), "Sarah Jones")
    assert (
        line
        == "Sarah would like to remind you to take your heart tablets at 8 am every day. Is that alright?"
    )
    assert consent_line(reminder(), None).startswith("Your family would like to remind you to")
    assert first_name("   ") == "Your family"


def test_due_consent_question_always_listens():
    occ = {"id": 7, "purpose": "consent", "reminders": reminder(confirm=False, creator={"full_name": "Sam"})}
    due = due_reminder("Tess", occ)
    assert due.model_dump() == {
        "occurrence_id": 7,
        "confirm": True,
        "purpose": "consent",
        "text": "Sam would like to remind you to take your heart tablets at 8 am every day. Is that alright?",
    }
    remind = due_reminder("Tess", {**occ, "purpose": "remind"})
    assert (remind.text, remind.confirm, remind.purpose) == (
        "Tess, it's time to take your heart tablets.",
        False,
        "remind",
    )


# ---------- consent through the pillow ----------


def test_consent_is_asked_by_day_once_a_day_while_pending():
    pending = reminder(consent="pending")
    day = WEEK[2]
    assert consent_slot_today(pending, TZ, at(day, 8, 59)) is None  # never early in the morning
    assert consent_slot_today(pending, TZ, at(day, 14)) == at(day, 9)  # one slot a day: 09:00
    assert consent_slot_today(pending, TZ, at(day, 9) + CONSENT_ASK_WINDOW) is None  # nor at night
    for answered in ("agreed", "declined"):
        assert consent_slot_today(reminder(consent=answered), TZ, at(day, 14)) is None
    assert consent_slot_today(reminder(consent="pending", active=False), TZ, at(day, 14)) is None


def test_no_consent_question_for_a_one_off_already_past():
    once = reminder(consent="pending", on_date=WEEK[2].isoformat(), time_of_day="10:00")
    assert consent_slot_today(once, TZ, at(WEEK[2], 9, 30)) == at(WEEK[2], 9)
    assert consent_slot_today(once, TZ, at(WEEK[2], 10)) is None


def test_consent_question_is_held_retried_later_then_left_for_tomorrow():
    due = at(WEEK[2], 9)
    occ = {
        "purpose": "consent",
        "status": "waiting",
        "attempts": 0,
        "due_at": due.isoformat(),
        "last_asked_at": None,
    }
    assert next_step(occ, False, "in_bed", due + timedelta(hours=2)) is None  # she is still in bed
    asked = due + timedelta(hours=2)
    first = next_step(occ, False, "awake", asked)
    assert first.status == "due" and first.buzz
    retry = {**occ, "attempts": 1, "last_asked_at": asked.isoformat()}
    assert next_step(retry, False, "awake", asked + CONSENT_RETRY_AFTER - timedelta(seconds=1)) is None
    assert next_step(retry, False, "awake", asked + CONSENT_RETRY_AFTER).fields["attempts"] == MAX_ASKS
    assert next_step(retry, False, "awake", due + CONSENT_ASK_WINDOW).status == "missed"


@pytest.mark.parametrize(
    ("outcome", "attempts", "reply", "expected"),
    [
        ("done", 1, "yes please", ("done", "agreed")),
        ("not_done", 1, "no thank you", ("done", "declined")),
        ("not_done", 1, None, ("waiting", None)),  # a mumble with no words: ask again
        ("no_answer", 1, None, ("waiting", None)),
        ("no_answer", MAX_ASKS, None, ("missed", None)),  # twice today: tomorrow
        ("announced", 1, None, ("waiting", None)),  # said without listening: ask again
        ("distress", 1, "help", ("missed", None)),  # Night Watch takes over
    ],
)
def test_consent_result(outcome, attempts, reply, expected):
    assert consent_result(outcome, attempts, reply) == expected


# ---------- the calendar ----------


def test_calendar_entries_carry_the_remind_status_and_sort_by_time():
    weekdays = reminder(id=2, days=[1, 2, 3, 4, 5], time_of_day="07:30", consent="pending")
    once = reminder(id=3, on_date="2026-11-02", time_of_day="07:00", confirm=False)
    occurrences = [
        {
            "reminder_id": 2,
            "due_at": at(WEEK[1], 7, 30).astimezone(ZoneInfo("UTC")).isoformat(),
            "status": "done",
        }
    ]
    entries = calendar_entries([weekdays, once], occurrences, SUN_NOV_1, WEEK[2], TZ)
    assert [(e.reminder_id, e.date, e.recurring, e.consent, e.status) for e in entries] == [
        (3, WEEK[1], False, "agreed", None),
        (2, WEEK[1], True, "pending", "done"),
        (2, WEEK[2], True, "pending", None),
    ]


def test_calendar_range_is_inclusive_and_at_most_two_months():
    assert CalendarRange(start=SUN_NOV_1, end=SUN_NOV_1).end == SUN_NOV_1
    longest = SUN_NOV_1 + timedelta(days=CALENDAR_MAX_DAYS - 1)
    assert CalendarRange(start=SUN_NOV_1, end=longest).end == longest
    for end in (SUN_NOV_1 - timedelta(days=1), longest + timedelta(days=1)):
        with pytest.raises(ValidationError):
            CalendarRange(start=SUN_NOV_1, end=end)


# ---------- creating and changing ----------


def test_new_reminders_wait_for_her_consent():
    made = ReminderCreate(
        label="call Sarah", time_of_day="18:30", on_date="2026-11-01", channels=["sms", "voice", "sms"]
    )
    assert made.to_fields(created_by="c1") == {
        "label": "call Sarah",
        "kind": "custom",
        "time_of_day": "18:30",
        "days": [1, 2, 3, 4, 5, 6, 7],
        "on_date": "2026-11-01",
        "confirm": False,
        "channels": ["sms", "voice"],
        "consent": "pending",
        "created_by": "c1",
    }
    for bad in ({"channels": []}, {"channels": ["pigeon"]}, {"time_of_day": "25:00"}, {"on_date": "soon"}):
        with pytest.raises(ValidationError):
            ReminderCreate(**{"label": "call Sarah", "time_of_day": "18:30", **bad})


def test_changing_what_or_when_asks_her_again():
    current = Reminder.from_row(reminder(consent="agreed", consent_at="2026-10-30T10:00:00+00:00"))
    reset = {"consent": "pending", "consent_at": None}
    assert ReminderUpdate(time_of_day="09:00").to_fields(current) == {"time_of_day": "09:00", **reset}
    assert ReminderUpdate(label="take your tablets").to_fields(current) == {
        "label": "take your tablets",
        **reset,
    }
    assert ReminderUpdate(on_date="2026-11-02").to_fields(current) == {"on_date": "2026-11-02", **reset}
    assert ReminderUpdate(days=[1]).to_fields(current) == {"days": [1], **reset}


def test_skipping_pausing_or_channels_keep_her_consent():
    current = Reminder.from_row(reminder())
    patch = ReminderUpdate(
        skip_dates=["2026-11-04", "2026-11-03"], active=False, confirm=False, channels=["voice", "email"]
    )
    assert patch.to_fields(current) == {
        "skip_dates": ["2026-11-03", "2026-11-04"],
        "active": False,
        "confirm": False,
        "channels": ["voice", "email"],
    }


def test_resending_unchanged_values_changes_nothing():
    current = Reminder.from_row(reminder())
    same = ReminderUpdate(
        label="take your heart tablets", time_of_day="08:00", on_date=None, days=[7, 1, 2, 3, 4, 5, 6]
    )
    assert same.to_fields(current) == {}
    once = Reminder.from_row(reminder(on_date="2026-11-02"))
    assert ReminderUpdate(on_date=None).to_fields(once) == {
        "on_date": None,
        "consent": "pending",
        "consent_at": None,
    }


def test_reminder_reads_hh_mm_and_who_set_it_up():
    row = reminder(time_of_day="18:30:00", creator={"full_name": "Test User"}, skip_dates=["2026-11-03"])
    out = Reminder.from_row(row).model_dump(mode="json")
    assert out["time_of_day"] == "18:30" and out["created_by_name"] == "Test User"
    assert out["skip_dates"] == ["2026-11-03"] and out["on_date"] is None
    assert Reminder.from_row(reminder()).created_by_name is None
