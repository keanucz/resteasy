"""Her personal night baseline from the past week of trips (plain code, no Supabase)."""

from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.agents.baseline import build_baseline
from app.agents.night_summary import summarize_night

TZ = "America/Los_Angeles"
Z = ZoneInfo(TZ)
NIGHT = datetime(2026, 10, 23, 18, 0, tzinfo=Z)  # the night being looked at starts Fri 23 Oct, 18:00


def trip(day, hh, mm, minutes):
    return {"left_at": datetime(2026, 10, day, hh, mm, tzinfo=Z).isoformat(), "trip_min": minutes}


# Szymon's demo week for mum (backend/supabase/demo_week.sql), the nights before Fri 23 Oct
DEMO_WEEK = [trip(18, 2, 14, 7.0), trip(19, 3, 5, 8.0), trip(20, 1, 48, 6.0), trip(20, 4, 40, 9.0),
             trip(21, 3, 12, 31.0), trip(22, 2, 30, 7.0), trip(23, 1, 55, 25.0)]


def test_demo_week_learns_her_usual_trip_plus_a_margin():
    b = build_baseline(DEMO_WEEK, NIGHT, TZ, owner_timeout_min=20)
    assert not b.learning
    assert (b.usual_trips, b.usual_nights, b.usual_trip_min) == (5, 4, 9)
    assert b.learned_timeout_min == 14 and b.checkin_timeout_min == 14
    assert b.usual_hours() == "01:48-04:40"
    assert b.long_trips == (("Wed 03:12", 31), ("Fri 01:55", 25))  # never part of the usual
    assert b.as_dict()["mode"] == "learned" and b.as_dict()["trips"] == 7


def test_learning_mode_keeps_the_owners_wait_until_a_week_of_trips():
    b = build_baseline(DEMO_WEEK[:3], NIGHT, TZ, owner_timeout_min=20)
    assert b.learning and b.checkin_timeout_min == 20 and b.learned_timeout_min is None
    # five short trips but all on two nights is still not a week
    two_nights = [trip(21, 1, m, 6.0) for m in range(0, 50, 10)] + [trip(22, 2, 0, 6.0)]
    assert build_baseline(two_nights, NIGHT, TZ, 20).learning


def test_trips_outside_the_window_or_in_the_daytime_are_ignored():
    rows = [*DEMO_WEEK, trip(15, 2, 0, 5.0), trip(24, 3, 0, 5.0), trip(21, 14, 0, 5.0)]
    assert build_baseline(rows, NIGHT, TZ, 20).trips == 7


def test_shorter_wait_wins_between_owner_and_learned():
    assert build_baseline(DEMO_WEEK, NIGHT, TZ, owner_timeout_min=30).checkin_timeout_min == 14
    assert build_baseline(DEMO_WEEK, NIGHT, TZ, owner_timeout_min=1).checkin_timeout_min == 1  # a demo value


def test_learned_wait_is_clamped_to_the_guardian_bounds():
    quick = [trip(d, 2, 0, 2.0) for d in range(17, 23)]
    assert build_baseline(quick, NIGHT, TZ, 20).learned_timeout_min == 10
    slow = [trip(d, 2, 0, 19.5) for d in range(17, 23)]
    b = build_baseline(slow, NIGHT, TZ, 20)
    assert b.learned_timeout_min == 25 and b.checkin_timeout_min == 20
    assert any("close to the 20-min check-in wait" in line for line in b.drift(1))


def test_unusual_hour_follows_the_night_clock():
    b = build_baseline(DEMO_WEEK, NIGHT, TZ, 20)  # usual 01:48-04:40
    assert not b.unusual_hour(time(1, 0)) and not b.unusual_hour(time(5, 30))
    assert b.unusual_hour(time(23, 30)) and b.unusual_hour(time(6, 0))
    assert not build_baseline(DEMO_WEEK[:3], NIGHT, TZ, 20).unusual_hour(time(23, 30))  # learning


def test_drift_reports_more_trips_and_the_long_ones():
    b = build_baseline(DEMO_WEEK, NIGHT, TZ, 20)  # 1 trip a night
    lines = b.drift(3)
    assert lines[0].startswith("3 trips last night; her usual is 1 a night")
    assert "2 trips over 20 min" in lines[1] and "31 min on Wed 03:12" in lines[1]
    assert not any("trips last night" in line for line in b.drift(1))


def test_summary_carries_the_baseline_and_flags_an_odd_hour():
    events = [{"event_type": "bed_exit", "device_ts": datetime(2026, 10, 23, 23, 20, tzinfo=Z).isoformat()},
              {"event_type": "bed_return", "device_ts": datetime(2026, 10, 23, 23, 27, tzinfo=Z).isoformat()}]
    s = summarize_night(events, TZ, build_baseline(DEMO_WEEK, NIGHT, TZ, 20))
    assert s["baseline"]["checkin_timeout_min"] == 14
    assert "got up at 23:20, over an hour outside her usual 01:48-04:40" in s["unusual"]
    assert any("not counted as usual" in line for line in s["unusual"])
    assert "baseline" not in summarize_night(events, TZ)
