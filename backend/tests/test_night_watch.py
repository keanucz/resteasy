"""Night Watch against the simulator's scripted nights (sim/pillow_sim.py) and a few edge cases."""

import importlib.util
from datetime import datetime
from pathlib import Path

import pytest

from app.agents.night_watch import (
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

NIGHT = datetime(2026, 10, 24, 23, 0).timestamp()  # scenarios start at 23:00 local
DAY = datetime(2026, 10, 24, 13, 0).timestamp()


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
    assert exit_min == pytest.approx(60.5, abs=0.02)  # head off at 60, confirmed after 30 s
    assert first(log, lambda a: isinstance(a, StartCheckin)) == pytest.approx(80, abs=0.02)  # from head-off
    alerts = [(m, a.channel) for m, a in log if isinstance(a, Alert)]
    assert alerts == [(pytest.approx(80, abs=0.02), "pillow"), (pytest.approx(82, abs=0.02), "sms"),
                      (pytest.approx(84, abs=0.02), "call")]
    kid = [a for _, a in log if isinstance(a, Command) and a.pillow_id == "kid" and a.cmd == "vibrate"]
    assert len(kid) == 1
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
    assert [a.channel for _, a in log if isinstance(a, Alert)] == ["pillow"]
    assert "family_ack" in events(log)
    assert any(isinstance(a, Say) and "Sarah knows" in a.text for _, a in log)


def test_tap_during_checkin_cancels_it():
    nw = NightWatch()
    nw.state, nw._left_at = State.CHECK_IN, NIGHT
    acts = nw.observe({"ts": NIGHT + 1, "head_on": False, "keys": {"fine": True}})
    assert any(isinstance(a, CancelCheckin) for a in acts) and nw.state is State.UP


def test_daytime_is_not_watched_unless_quiet_hours_are_off():
    _, log = run(scenario("no_return"), start=DAY)
    assert not any(isinstance(a, StartCheckin) for _, a in log)
    _, log = run(scenario("no_return"), start=DAY, config=NightWatchConfig(quiet_hours=None))
    assert any(isinstance(a, StartCheckin) for _, a in log)


def test_a_brief_head_lift_is_not_a_bed_exit():
    phases = [(0, sim.ASLEEP), (10, sim.OUT_OF_BED), (10.33, sim.ASLEEP), (20, sim.ASLEEP)]  # 20 s off
    _, log = run(phases)
    assert "bed_exit" not in events(log)
