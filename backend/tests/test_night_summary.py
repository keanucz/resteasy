"""Plain-code summary of one night from the events table (for the Morning Brief and the family agent)."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.agents.night_summary import last_night_window, pending_goodnight, summarize_night

TZ = "America/Los_Angeles"
Z = ZoneInfo(TZ)


def ts(day, hh, mm=0):
    return datetime(2026, 10, day, hh, mm, tzinfo=Z).isoformat()


def ev(day, hh, mm, kind, **data):
    return {"event_type": kind, "device_ts": ts(day, hh, mm), "data": data}


def test_last_night_window_in_the_morning_is_yesterday_evening_to_now():
    now = datetime(2026, 10, 25, 6, 0, tzinfo=Z).timestamp()
    start, end = last_night_window(now, TZ)
    assert (start.hour, start.day) == (18, 24) and end.timestamp() == now


def test_last_night_window_in_the_afternoon_is_the_whole_previous_night():
    now = datetime(2026, 10, 25, 15, 0, tzinfo=Z).timestamp()
    start, end = last_night_window(now, TZ)
    assert (start.day, start.hour, end.day, end.hour) == (24, 18, 25, 12)


def test_an_earlier_night_by_its_evening():
    """At 22:00 the latest night has only just begun; `evening` reads yesterday's whole night."""
    tz = ZoneInfo(TZ)
    now = datetime(2026, 10, 24, 22, 0, tzinfo=tz).timestamp()
    start, end = last_night_window(now, TZ, date(2026, 10, 23))
    assert start == datetime(2026, 10, 23, 18, 0, tzinfo=tz)
    assert end == datetime(2026, 10, 24, 12, 0, tzinfo=tz)


def test_summary_pairs_trips_and_finds_the_longest():
    events = [
        ev(24, 22, 40, "lay_down"), ev(25, 1, 0, "bed_exit"), ev(25, 1, 6, "bed_return"),
        ev(25, 3, 10, "bed_exit"), ev(25, 3, 30, "no_return"),
        ev(25, 3, 32, "checkin_result", escalate=False),
        ev(25, 3, 41, "bed_return"), ev(25, 7, 5, "got_up"),
    ]
    s = summarize_night(events, TZ)
    assert s["trips"] == [{"left": "01:00", "back": "01:06", "min": 6},
                          {"left": "03:10", "back": "03:41", "min": 31}]
    assert s["longest_trip_min"] == 31 and s["trip_count"] == 2
    assert s["checkins"] == 1 and s["escalations"] == 0
    assert s["lay_down"] == "22:40" and s["got_up"] == "07:05"


def test_summary_counts_escalations_and_open_trips():
    events = [ev(24, 23, 0, "lay_down"), ev(25, 2, 0, "bed_exit"), ev(25, 2, 20, "no_return"),
              ev(25, 2, 21, "checkin_result", escalate=True), ev(25, 2, 21, "escalation_step", channel="app"),
              ev(25, 2, 24, "family_ack", contact="Sarah")]
    s = summarize_night(events, TZ)
    assert s["trips"] == [{"left": "02:00", "back": None, "min": None}]
    assert s["escalations"] == 1 and s["acknowledged_by"] == ["Sarah"]
    assert s["unusual"]  # an escalation is always worth a line


def test_summary_of_a_quiet_night_has_nothing_unusual():
    s = summarize_night([ev(24, 22, 30, "lay_down"), ev(24, 22, 50, "asleep"), ev(25, 7, 0, "got_up")], TZ)
    assert s["trip_count"] == 0 and s["unusual"] == []
    assert s["asleep"] == "22:50"


def test_restless_spells_are_counted():
    spell = [ev(24, 23, 0, "lay_down"), ev(24, 23, 30, "restless"), ev(24, 23, 50, "settled")]
    s = summarize_night(spell, TZ)
    assert s["restless_spells"] == 1


def test_pending_goodnight_is_the_last_unplayed_message():
    assert pending_goodnight([]) is None
    queued = ev(24, 19, 0, "goodnight_queued", message="Night night Gran", from_name="Ellie")
    assert pending_goodnight([queued])["message"] == "Night night Gran"
    played = ev(24, 22, 40, "goodnight_played", message="Night night Gran")
    assert pending_goodnight([queued, played]) is None
    later = ev(24, 23, 0, "goodnight_queued", message="Sleep well", from_name="Sarah")
    assert pending_goodnight([queued, played, later])["from_name"] == "Sarah"
