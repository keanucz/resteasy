"""The sleep-quality and key events of coord/CONTRACT.md section 2 that Night Watch doesn't derive:
restless, asleep, key_talk, key_family."""

from app.agents.sleep_events import (
    ASLEEP_S,
    DEMO_ASLEEP_S,
    DEMO_HEAD_OFF_GRACE_S,
    DEMO_RESTLESS_MOTION,
    HEAD_OFF_GRACE_S,
    RESTLESS_S,
    SleepTracker,
)

T0 = 1_792_815_000.0


def feed(tracker, start, seconds, **fields):
    """One report per second for `seconds` from `start`; returns (next ts, events)."""
    out = []
    for t in range(seconds):
        out += tracker.observe({"ts": start + t, "head_on": True, "motion": 0.03, "keys": {}, **fields})
    return start + seconds, out


def types(events):
    return [e.type for e in events]


def test_asleep_after_15_quiet_minutes_in_bed():
    tr = SleepTracker()
    _, before = feed(tr, T0, ASLEEP_S - 1, motion=0.03)
    assert "asleep" not in types(before)
    _, after = feed(tr, T0 + ASLEEP_S - 1, 2, motion=0.03)
    assert types(after) == ["asleep"]


def test_asleep_fires_once_until_she_leaves_the_bed():
    tr = SleepTracker()
    ts, ev = feed(tr, T0, ASLEEP_S + 600, motion=0.03)
    assert types(ev).count("asleep") == 1
    ts, _ = feed(tr, ts, HEAD_OFF_GRACE_S + 1, head_on=False)  # longer than a roll-over: she left
    _, ev = feed(tr, ts, ASLEEP_S + 1, motion=0.03)
    assert types(ev) == ["asleep"]


def test_restless_after_10_minutes_of_tossing():
    tr = SleepTracker()
    _, ev = feed(tr, T0, RESTLESS_S + 1, motion=0.55)
    assert types(ev) == ["restless"]
    assert ev[0].data["motion_avg"] > 0.35


def test_a_short_toss_is_not_restless():
    tr = SleepTracker()
    ts, ev = feed(tr, T0, 120, motion=0.6)  # 2 min of tossing ...
    _, more = feed(tr, ts, RESTLESS_S, motion=0.1)  # ... in an otherwise calm 10 minutes
    assert "restless" not in types(ev + more)


def test_restless_needs_a_head_on_the_pillow():
    tr = SleepTracker()
    _, ev = feed(tr, T0, RESTLESS_S + 1, motion=0.9, head_on=False)
    assert ev == []


def test_settling_after_restless_is_reported():
    tr = SleepTracker()
    ts, ev = feed(tr, T0, RESTLESS_S + 1, motion=0.55)
    assert types(ev) == ["restless"]
    _, ev = feed(tr, ts, RESTLESS_S + 1, motion=0.05)
    assert types(ev)[0] == "settled"


def test_key_presses_fire_on_the_rising_edge_only():
    tr = SleepTracker()
    held = {"talk": True, "fine": False, "family": False}
    ts, ev = feed(tr, T0, 3, keys=held)
    assert types(ev) == ["key_talk"]
    ts, ev = feed(tr, ts, 1, keys={"talk": False, "fine": False, "family": True})
    assert types(ev) == ["key_family"]


def test_key_fine_is_left_to_night_watch():
    tr = SleepTracker()
    _, ev = feed(tr, T0, 2, keys={"fine": True})
    assert ev == []


def test_null_readings_are_skipped_not_counted():
    tr = SleepTracker()
    _, ev = feed(tr, T0, ASLEEP_S + 1, motion=None)
    assert ev == []


def test_rolling_off_the_pillow_briefly_keeps_the_sleep_session():
    """Keanu's roll-off case: a head-off gap shorter than the grace period is still the same sleep."""
    tr = SleepTracker()
    ts, ev = feed(tr, T0, ASLEEP_S + 1, motion=0.03)
    assert types(ev) == ["asleep"]
    ts, ev = feed(tr, ts, HEAD_OFF_GRACE_S - 1, head_on=False)  # rolls over for just under the grace
    ts, more = feed(tr, ts, ASLEEP_S + 1, motion=0.03)
    assert "asleep" not in types(ev + more)  # same session: no second 'asleep'


def test_a_longer_absence_ends_the_sleep_session():
    tr = SleepTracker()
    ts, _ = feed(tr, T0, ASLEEP_S + 1, motion=0.03)
    ts, _ = feed(tr, ts, HEAD_OFF_GRACE_S + 1, head_on=False)
    _, ev = feed(tr, ts, ASLEEP_S + 1, motion=0.03)
    assert types(ev) == ["asleep"]


# ---------- demo timings (PILLOW_DEMO_TIMINGS=1) ----------


def test_demo_restless_when_she_moves_and_settled_when_she_stops():
    tr = SleepTracker(demo=True)
    ts, ev = feed(tr, T0, 1, motion=DEMO_RESTLESS_MOTION + 0.1)
    assert "restless" not in types(ev)  # one bump of the bedside unit isn't enough
    ts, ev = feed(tr, ts, 1, motion=DEMO_RESTLESS_MOTION + 0.1)
    assert types(ev) == ["restless"]
    ts, ev = feed(tr, ts, 5, motion=0.5)
    assert types(ev) == []  # still restless, said once
    ts, ev = feed(tr, ts, 2, motion=0.02)
    assert types(ev) == ["settled"]


def test_demo_asleep_after_a_few_quiet_seconds():
    tr = SleepTracker(demo=True)
    _, ev = feed(tr, T0, DEMO_ASLEEP_S + 1, motion=0.02)
    assert types(ev) == ["asleep"]


def test_demo_leaving_the_bed_while_restless_closes_the_spell():
    tr = SleepTracker(demo=True)
    ts, ev = feed(tr, T0, 2, motion=0.6)
    assert types(ev) == ["restless"]
    _, ev = feed(tr, ts, DEMO_HEAD_OFF_GRACE_S + 1, head_on=False)
    assert types(ev) == ["settled"]  # so lying down again shows asleep, not the old restless
