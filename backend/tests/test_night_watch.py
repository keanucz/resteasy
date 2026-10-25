"""Night Watch against the simulator's scripted nights (sim/pillow_sim.py) and a few edge cases."""

import importlib.util
from dataclasses import replace
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.agents.night_watch import (
    BED_RETURN_S,
    DEMO_TIMINGS,
    Alert,
    CancelCheckin,
    Command,
    Event,
    NightWatch,
    NightWatchConfig,
    Say,
    StartCheckin,
    State,
)

_SIM = Path(__file__).resolve().parents[2] / "sim" / "pillow_sim.py"
_spec = importlib.util.spec_from_file_location("pillow_sim", _SIM)
sim = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sim)

TZ = ZoneInfo("America/Los_Angeles")  # NightWatchConfig default
NIGHT = datetime(2026, 10, 24, 23, 0, tzinfo=TZ).timestamp()  # scenarios start at 23:00 there
DAY = datetime(2026, 10, 24, 13, 0, tzinfo=TZ).timestamp()


def run(phases, *, checkin="silent", start=NIGHT, ack_after_min=None, config=None, end_min=None):
    """Play `phases` at 1 sample/s through Night Watch. Returns (watch, [(minute, action)])."""
    nw = NightWatch(config or NightWatchConfig())
    log = []
    escalated_at = None
    end = end_min if end_min is not None else phases[-1][0]
    for second in range(int(end * 60) + 1):
        minute, ts = second / 60, start + second
        acts = nw.observe({"ts": ts, **sim.state_at(phases, minute)})
        if any(isinstance(a, StartCheckin) for a in acts):
            acts += nw.checkin_done(ts, escalate=checkin == "silent",
                                    reason="She didn't answer." if checkin == "silent" else "")
        if escalated_at is None and nw.state is State.ESCALATING:
            escalated_at = minute
        if ack_after_min is not None and escalated_at is not None and minute == escalated_at + ack_after_min:
            acts += nw.family_acknowledged(ts, "Sarah")
        log += [(minute, a) for a in acts]
    return nw, log


def scenario(name):
    return sim.SCENARIOS[name][1]


def events(log):
    return [a.type for _, a in log if isinstance(a, Event)]


def first(log, pred):
    return next(m for m, a in log if pred(a))


def test_good_night_lights_the_path_and_never_checks_in():
    nw, log = run(scenario("good_night"))
    assert events(log)[:3] == ["lay_down", "bed_exit", "bed_return"]
    assert not any(isinstance(a, (StartCheckin, Alert)) for _, a in log)
    lights = [a.args["brightness_pct"] for _, a in log if isinstance(a, Command) and a.cmd == "set_light"]
    assert lights == [20, 0]
    assert nw.state is State.IN_BED


def test_no_return_checks_in_after_20_min_then_escalates_up_the_ladder():
    nw, log = run(scenario("no_return"))
    exit_min = first(log, lambda a: isinstance(a, Event) and a.type == "bed_exit")
    assert exit_min == pytest.approx(60 + 10 / 60, abs=0.02)  # head off at 60, confirmed after 10 s
    assert first(log, lambda a: isinstance(a, StartCheckin)) == pytest.approx(80, abs=0.02)  # from head-off
    alerts = [(m, a.channel) for m, a in log if isinstance(a, Alert)]
    assert alerts == [(pytest.approx(80, abs=0.02), "app"), (pytest.approx(82, abs=0.02), "sms"),
                      (pytest.approx(84, abs=0.02), "call")]
    assert all(a.pillow_id == "mum" for _, a in log if isinstance(a, Command))  # one pillow only
    assert "She didn't answer." in next(a.message for _, a in log if isinstance(a, Alert))
    assert "ladder_exhausted" in events(log)


def test_back_in_bed_during_escalation_stands_down_and_tells_family():
    phases = [(0, sim.ASLEEP), (5, sim.EMPTY_ROOM), (30, sim.ASLEEP), (40, sim.ASLEEP)]
    nw, log = run(phases)  # up at 5, silent check-in at 25, back in bed at 30
    back = [a for m, a in log if isinstance(a, Alert) and "back in bed" in a.message]
    assert [a.contact for a in back] == ["Sarah"]
    assert nw.state is State.IN_BED


def test_tap_during_escalation_tells_family_she_is_okay():
    nw, log = run(scenario("talk_then_fine"))  # up at 5, check-in at 25 (silent), taps at 30
    assert first(log, lambda a: isinstance(a, StartCheckin)) == pytest.approx(25, abs=0.02)
    told = [a.message for _, a in log if isinstance(a, Alert) and a.channel == "sms" and "okay" in a.message]
    assert told == ["Mum tapped her pillow to say she's okay."]
    assert nw.state is State.IN_BED


def test_every_no_return_checks_in_again_and_never_alarms_while_she_says_fine():
    phases = [(0, sim.ASLEEP), (5, sim.EMPTY_ROOM), (70, sim.EMPTY_ROOM)]
    nw, log = run(phases, checkin="fine")
    checkins = [m for m, a in log if isinstance(a, StartCheckin)]
    assert checkins == [pytest.approx(m, abs=0.02) for m in (25, 45, 65)]
    alerts = [(m, a.channel, a.message) for m, a in log if isinstance(a, Alert)]
    assert len(alerts) == 1  # one heads-up after the second "fine", no alarm ladder
    m, channel, message = alerts[0]
    assert m == pytest.approx(45, abs=0.02) and channel == "sms" and message.startswith("Heads-up")
    assert not any(isinstance(a, Command) and a.cmd == "vibrate" for _, a in log)


def test_family_ack_stops_the_ladder():
    nw, log = run(scenario("no_return"), ack_after_min=1)
    assert [a.channel for _, a in log if isinstance(a, Alert)] == ["app"]
    assert "family_ack" in events(log)
    assert any(isinstance(a, Say) and "Sarah knows" in a.text for _, a in log)


def test_tap_during_checkin_cancels_it():
    nw = NightWatch()
    nw.state, nw._left_at, nw._on_a_trip = State.CHECK_IN, NIGHT, True
    acts = nw.observe({"ts": NIGHT + 1, "head_on": False, "keys": {"fine": True}})
    assert any(isinstance(a, CancelCheckin) for a in acts) and nw.state is State.UP


def test_daytime_is_not_watched_unless_quiet_hours_are_off():
    _, log = run(scenario("no_return"), start=DAY)
    assert not any(isinstance(a, StartCheckin) for _, a in log)
    _, log = run(scenario("no_return"), start=DAY, config=NightWatchConfig(quiet_hours=None))
    assert any(isinstance(a, StartCheckin) for _, a in log)


def test_a_brief_head_lift_is_not_a_bed_exit():
    phases = [(0, sim.ASLEEP), (10, sim.OUT_OF_BED), (10.1, sim.ASLEEP), (20, sim.ASLEEP)]  # 6 s off
    _, log = run(phases)
    assert "bed_exit" not in events(log)


def test_quiet_hours_follow_her_timezone_not_the_servers():
    london = NightWatchConfig(timezone="Europe/London")
    start = datetime(2026, 10, 24, 23, 0, tzinfo=ZoneInfo("Europe/London")).timestamp()  # 15:00 in LA
    _, log = run(scenario("no_return"), start=start, config=london)
    assert any(isinstance(a, StartCheckin) for _, a in log)


def test_equal_quiet_start_and_end_watch_all_day():
    always = NightWatchConfig(quiet_hours=(time(0), time(0)))
    _, log = run(scenario("no_return"), start=DAY, config=always)
    assert any(isinstance(a, StartCheckin) for _, a in log)


def test_paused_monitoring_starts_no_watch():
    _, log = run(scenario("no_return"), config=NightWatchConfig(paused=True))
    assert not any(isinstance(a, (StartCheckin, Alert)) for _, a in log)


@pytest.mark.parametrize("saved, next_state", [(State.IN_BED, State.UP), (State.CHECK_IN, State.CHECK_IN)])
def test_resume_after_restart(saved, next_state):
    nw = NightWatch()
    nw.resume(saved, since=NIGHT)
    acts = []
    for second in range(0, 40):  # 40 s with her head off the pillow
        acts += nw.observe({"ts": NIGHT + 60 + second, **sim.EMPTY_ROOM})
    assert nw.state is next_state  # in bed -> she gets up; mid check-in -> asked again at once
    if saved is State.CHECK_IN:
        assert isinstance(acts[1], StartCheckin)


def test_every_contact_gets_the_app_alert_first_then_sms_and_calls_in_turn():
    cfg = NightWatchConfig(contacts=("Sarah", "Tom"))
    _, log = run(scenario("no_return"), config=cfg)
    steps = [(round(m), a.channel, a.contact) for m, a in log if isinstance(a, Alert)]
    assert steps == [(80, "app", "Sarah"), (80, "app", "Tom"), (82, "sms", "Sarah"), (84, "call", "Sarah"),
                     (86, "sms", "Tom"), (88, "call", "Tom")]


def test_the_ladder_skips_the_channels_a_contact_turned_off():
    cfg = NightWatchConfig(contacts=("Sarah", "Tom"),
                           channels={"Sarah": frozenset({"sms"}), "Tom": frozenset({"app", "call"})})
    _, log = run(scenario("no_return"), config=cfg)
    steps = [(round(m), a.channel, a.contact) for m, a in log if isinstance(a, Alert)]
    assert steps == [(80, "app", "Tom"), (82, "sms", "Sarah"), (84, "call", "Tom")]


def test_distress_in_a_checkin_phones_and_texts_everyone_at_once():
    nw = NightWatch(NightWatchConfig(contacts=("Sarah", "Tom"), channels={"Tom": frozenset({"app", "sms"})}))
    ts, _ = feed(nw, NIGHT, 10, True)
    ts, _ = feed(nw, ts, 20 * 60 + 40, False)
    acts = nw.checkin_done(ts, escalate=True, reason='She said: "Help, I have fallen"', distress=True)
    assert [(a.channel, a.contact) for a in acts if isinstance(a, Alert)] == [
        ("app", "Sarah"), ("app", "Tom"), ("call", "Sarah"), ("sms", "Sarah"), ("sms", "Tom")]  # no call: Tom
    step = next(a for a in acts if isinstance(a, Event) and a.type == "escalation_step")
    assert step.data["kind"] == "distress"
    call = next(a for a in acts if isinstance(a, Alert) and a.channel == "call")
    assert "asked for help. She got up at 23:00." in call.message and "Help, I have fallen" in call.message
    later = nw.observe({"ts": ts + 2 * 60 + 1, "head_on": False, "keys": {"fine": False}})
    assert [a for a in later if isinstance(a, Alert)] == []  # everyone already has the call and the text


def test_a_silent_checkin_keeps_the_gentle_ladder_even_if_distress_is_sent():
    nw = NightWatch(NightWatchConfig(contacts=("Sarah",)))
    ts, _ = feed(nw, NIGHT, 10, True)
    ts, _ = feed(nw, ts, 20 * 60 + 40, False)
    acts = nw.checkin_done(ts, escalate=True, reason="She didn't answer.")
    assert [a.channel for a in acts if isinstance(a, Alert)] == ["app"]


def test_a_gentle_distress_alert_starts_in_the_app():
    nw = NightWatch(NightWatchConfig(contacts=("Sarah",)))
    acts = nw.distress_heard(NIGHT, "Started from the app's alert debug.", urgent=False)
    assert [(a.channel, a.contact) for a in acts if isinstance(a, Alert)] == [("app", "Sarah")]


def feed(nw, start, seconds, head_on, fine=False):
    """One report per second for `seconds` from `start`. Returns (next start, actions)."""
    acts = []
    for t in range(seconds):
        acts += nw.observe({"ts": start + t, "head_on": head_on, "keys": {"fine": fine}})
    return start + seconds, acts


def escalating(nw, start=NIGHT):
    """In bed, up for good, check-in escalates. Returns the ts after it."""
    ts, _ = feed(nw, start, 10, True)
    ts, acts = feed(nw, ts, 20 * 60 + 40, False)
    assert any(isinstance(a, StartCheckin) for a in acts)
    nw.checkin_done(ts, escalate=True, reason="She didn't answer.")
    assert nw.state is State.ESCALATING
    return ts


def test_lying_down_before_quiet_hours_is_still_watched():
    evening = datetime(2026, 10, 24, 21, 30, tzinfo=TZ).timestamp()
    nw = NightWatch()
    ts, _ = feed(nw, evening, 10, True)
    assert nw.state is State.AWAKE  # 21:30: not watching yet
    acts = nw.tick(datetime(2026, 10, 24, 22, 0, tzinfo=TZ).timestamp())
    assert nw.state is State.IN_BED and acts[0].data["late_start"]
    up = datetime(2026, 10, 25, 2, 0, tzinfo=TZ).timestamp()
    _, acts = feed(nw, up, 40, False)
    assert "bed_exit" in [a.type for a in acts if isinstance(a, Event)]


def test_a_checkin_that_never_reports_back_escalates():
    nw = NightWatch()
    ts, _ = feed(nw, NIGHT, 10, True)
    ts, acts = feed(nw, ts, 20 * 60 + 40, False)
    assert nw.state is State.CHECK_IN
    assert nw.tick(ts + 60) == []  # still within the check-in's time
    acts = nw.tick(ts + 200)  # the board has gone quiet too: only the tick moves time on
    assert nw.state is State.ESCALATING
    assert any(isinstance(a, CancelCheckin) for a in acts)
    assert any(isinstance(a, Alert) and "didn't finish" in a.message for a in acts)


def test_fine_tap_counts_even_without_a_head_reading():
    nw = NightWatch()
    ts = escalating(nw)
    acts = nw.observe({"ts": ts + 1, "head_on": None, "keys": {"fine": True}})
    assert nw.state is State.UP and "key_fine" in events([(0, a) for a in acts])


def test_a_brief_head_reading_during_escalation_is_not_a_return():
    nw = NightWatch()
    ts = escalating(nw)
    ts, acts = feed(nw, ts, 10, True)
    ts, more = feed(nw, ts, 5, False)
    assert nw.state is State.ESCALATING and "bed_return" not in events([(0, a) for a in acts + more])
    _, acts = feed(nw, ts, BED_RETURN_S + 1, True)
    assert nw.state is State.IN_BED and "bed_return" in events([(0, a) for a in acts])


def test_reports_from_the_past_are_ignored():
    nw = NightWatch()
    ts, _ = feed(nw, NIGHT, 10, True)
    assert nw.observe({"ts": NIGHT - 100, "head_on": False, "keys": {"fine": True}}) == []
    assert nw.tick(NIGHT - 100) == []


# ---------- demo timings (PILLOW_DEMO_TIMINGS=1) ----------


def play(nw, start, head_by_second):
    """Feed one report a second, head on or off as listed; returns [(second, action)]."""
    out = []
    for second, head in enumerate(head_by_second):
        out += [(second, a) for a in nw.observe({"ts": start + second, "head_on": head, "keys": {}})]
    return out


def second_of(log, kind):
    return next(second for second, a in log if isinstance(a, Event) and a.type == kind)


def test_demo_timings_show_every_state_within_seconds():
    nw = NightWatch(timings=DEMO_TIMINGS)
    # the second reading that agrees decides: on = in bed; lifted at 10: up at the next reads off,
    # check-in 15 s after the lift; back on = back in bed
    log = play(nw, NIGHT, [True] * 10 + [False] * 20 + [True] * 5)
    assert second_of(log, "lay_down") == 1
    assert second_of(log, "bed_exit") == 12
    assert second_of(log, "no_return") == 25
    assert any(isinstance(a, StartCheckin) for s, a in log if s == 25)
    assert second_of(log, "bed_return") == 31
    assert nw.state is State.IN_BED


def test_demo_alerts_family_120_s_into_a_checkin_that_never_reports():
    nw = NightWatch(timings=DEMO_TIMINGS)
    play(nw, NIGHT, [True] * 4 + [False] * 20)  # check-in started at 19
    assert nw.tick(NIGHT + 138) == []
    acts = nw.tick(NIGHT + 139)
    assert isinstance(acts[1], CancelCheckin) and nw.state is State.ESCALATING
    assert [a.channel for a in acts if isinstance(a, Alert)] == ["app"]


def test_demo_a_spoken_fine_after_two_asks_still_counts():
    # A spoken answer is heard, judged and posted in well under 30 s; a 10 s limit lost real "I'm fine"s
    nw = NightWatch(timings=DEMO_TIMINGS)
    play(nw, NIGHT, [True] * 4 + [False] * 20)  # check-in started at 19
    nw.tick(NIGHT + 79)
    nw.checkin_done(NIGHT + 79, escalate=False, reason="She said she was fine.")
    assert nw.state is State.UP


def test_demo_asks_again_a_minute_after_she_says_fine():
    nw = NightWatch(timings=DEMO_TIMINGS)
    play(nw, NIGHT, [True] * 4 + [False] * 20)  # check-in started at 19
    assert nw.state is State.CHECK_IN
    nw.checkin_done(NIGHT + 24, escalate=False, reason="")
    assert nw.state is State.UP
    assert nw.tick(NIGHT + 24 + 59) == []  # not 15 s: a rehearsal mustn't reach the family heads-up
    assert any(isinstance(a, StartCheckin) for a in nw.tick(NIGHT + 24 + 60))


def test_default_timings_are_the_products():
    nw = NightWatch()
    log = play(nw, NIGHT, [True] * 6 + [False] * 12)
    assert second_of(log, "lay_down") == 5
    assert second_of(log, "bed_exit") == 16  # 10 s after the lift at 6
    assert nw.state is State.UP  # the check-in waits the owner's minutes, not seconds


def _up_and_said_fine(config: NightWatchConfig) -> tuple[NightWatch, float]:
    """In bed, up at +10 s, the check-in at +25 s, and she says she's fine at +30 s (demo timings)."""
    nw = NightWatch(config, DEMO_TIMINGS)
    for second in range(26):
        acts = nw.observe({"ts": NIGHT + second, "head_on": second < 10})
    assert any(isinstance(a, StartCheckin) for a in acts)
    nw.checkin_done(NIGHT + 30, escalate=False, reason="She said she was fine.")
    return nw, NIGHT + 30


def test_the_cooldown_holds_the_next_check_in():
    nw, done = _up_and_said_fine(NightWatchConfig(checkin_cooldown_min=10))
    held = [a for s in range(1, 600) for a in nw.observe({"ts": done + s, "head_on": False})]
    assert not any(isinstance(a, StartCheckin) for a in held)  # the 60 s recheck waits
    assert any(isinstance(a, StartCheckin) for a in nw.observe({"ts": done + 600, "head_on": False}))


def test_turning_the_cooldown_off_asks_again_at_once():
    nw, done = _up_and_said_fine(NightWatchConfig(checkin_cooldown_min=10))
    assert not any(isinstance(a, StartCheckin) for a in nw.observe({"ts": done + 60, "head_on": False}))
    nw.cfg = replace(nw.cfg, checkin_cooldown_min=0)
    assert any(isinstance(a, StartCheckin) for a in nw.observe({"ts": done + 61, "head_on": False}))


def test_fine_after_an_alert_from_awake_goes_back_to_awake():
    # A distress reply to a daytime reminder, then "I'm fine": no trip out of bed to watch
    nw = NightWatch(NightWatchConfig(), DEMO_TIMINGS)
    nw.distress_heard(DAY, "She said: \"help\"")
    assert nw.state is State.ESCALATING
    nw.fine_pressed(DAY + 30)
    assert nw.state is State.AWAKE
    later = [a for s in range(1, 300) for a in nw.tick(DAY + 30 + s)]
    assert not any(isinstance(a, StartCheckin) for a in later)


def test_fine_after_an_alert_on_a_trip_keeps_watching_the_trip():
    nw, done = _up_and_said_fine(NightWatchConfig())
    assert nw.state is State.UP
