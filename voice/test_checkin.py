"""Check-in rules against scripted replies, no audio.  uv run --with pytest pytest voice"""

from types import SimpleNamespace

import pytest

from checkin import Kind, classify, run_checkin


def fake(*replies):
    """speak/listen pair: each listen() returns the next scripted reply (None = silence)."""
    said, queue = [], list(replies)

    def speak(text, volume=1.0):
        said.append((text, volume))

    def listen(no_answer_s):
        r = queue.pop(0) if queue else None
        if r is None:
            return SimpleNamespace(text="", spoke=False)
        if r == "...":  # a mumble: speech detected, nothing transcribed
            return SimpleNamespace(text="", spoke=True)
        return SimpleNamespace(text=r, spoke=True)

    return speak, listen, said


@pytest.mark.parametrize("text,kind", [
    ("I'm doing okay.", Kind.FINE),
    ("Yeah, just going to the loo", Kind.FINE),
    ("I've fallen and I can't get up", Kind.DISTRESS),
    ("I'm not okay", Kind.DISTRESS),
    ("Where am I?", Kind.CONFUSED),
    ("the cat the cat", Kind.UNCLEAR),
])
def test_classify(text, kind):
    assert classify(text, True) is kind


def test_fine_first_try_stands_down():
    speak, listen, said = fake("I'm fine")
    out = run_checkin(speak, listen)
    assert not out.escalate and len(said) == 2


def test_distress_escalates_at_once_and_tells_her():
    speak, listen, said = fake("help, I've fallen")
    out = run_checkin(speak, listen, contact="Sarah")
    assert out.escalate and "fallen" in out.reason
    assert "getting Sarah" in said[-1][0] and len(said) == 2


def test_silence_three_louder_tries_then_warning_then_escalate():
    speak, listen, said = fake(None, None, None, None)
    out = run_checkin(speak, listen, contact="Sarah")
    assert out.escalate and out.reason == "She didn't answer."
    asks = [v for _, v in said[:3]]
    assert asks == sorted(asks) and asks[0] < asks[-1]
    assert "let Sarah know" in said[3][0]


def test_fine_during_warning_cancels():
    speak, listen, said = fake(None, None, None, "I'm fine, sorry")
    out = run_checkin(speak, listen)
    assert not out.escalate


def test_mumbling_escalates_as_unclear_not_silent():
    speak, listen, said = fake("...", "...", "...", "...")
    out = run_checkin(speak, listen)
    assert out.escalate and "couldn't understand" in out.reason
    assert "didn't quite catch" in said[1][0]


def test_confused_reorients_once_then_counts():
    speak, listen, said = fake("where am I?", "yes I'm okay now")
    out = run_checkin(speak, listen)
    assert not out.escalate and "at home" in said[1][0]


def test_confused_forever_still_ends():
    speak, listen, said = fake(*["where am I?"] * 10)
    out = run_checkin(speak, listen)
    # first ask, then 3 tries after the reorient, the warning, "letting Sarah know"
    assert out.escalate and len(said) == 1 + 3 + 1 + 1
