"""Check-in rules against scripted replies, no audio.  uv run --with pytest pytest voice"""

import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from checkin import _REORIENT, run_checkin
from judge import Kind, Verdict, classify


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
    ("No, I'm fine", Kind.FINE),
    ("I don't feel okay", Kind.DISTRESS),
    ("I'm not feeling good", Kind.DISTRESS),
    ("Yeah... no, I'm not", Kind.DISTRESS),
    ("I'm okay, I just can't move my leg", Kind.DISTRESS),
    ("I'm on the floor", Kind.DISTRESS),
    ("I feel dizzy", Kind.DISTRESS),
    ("I can't breathe", Kind.DISTRESS),
    ("Yes please, call her", Kind.DISTRESS),
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
    assert out.escalate and len(said) == 1 + 3 + 1 + 1 and "confused" in out.reason


def test_judge_wording_used_for_fine_but_not_distress():
    def judge(q, text):
        if "fallen" in text:
            return Verdict(Kind.DISTRESS, "a made-up distress line")
        return Verdict(Kind.FINE, "Lovely, take your time.")
    speak, listen, said = fake("I'm good")
    run_checkin(speak, listen, judge=judge)
    assert said[-1][0] == "Lovely, take your time."
    speak, listen, said = fake("I've fallen")
    run_checkin(speak, listen, judge=judge, contact="Sarah")
    assert "getting Sarah" in said[-1][0]


def test_reorient_line_is_fixed_not_the_judges():
    judge = lambda q, t: Verdict(Kind.CONFUSED, "Take two aspirin.") if "where" in t else Verdict(Kind.FINE)
    speak, listen, said = fake("where am I", "okay")
    run_checkin(speak, listen, judge=judge)
    assert said[1][0] == f"{_REORIENT} Are you alright?"


def test_fine_during_warning_needs_an_explicit_im_fine():
    for reply in ("Yes please, call her", "yeah"):  # agreeing to the call, not cancelling it
        speak, listen, _ = fake(None, None, None, reply)
        assert run_checkin(speak, listen).escalate


def test_a_broken_mic_or_network_escalates_instead_of_crashing():
    def listen(no_answer_s):
        raise ConnectionError("Cartesia unreachable")

    out = run_checkin(lambda text, volume=1.0: None, listen)
    assert out.escalate and "could not run" in out.reason


def test_claude_judge_falls_back_to_keywords_without_a_client(monkeypatch):
    import judge

    def no_client():
        raise TypeError("no ANTHROPIC_API_KEY")

    monkeypatch.setattr(judge, "_get_client", no_client)
    assert judge.claude_judge("Are you alright?", "I've fallen").kind is Kind.DISTRESS
    assert judge.claude_judge("Are you alright?", "I'm fine").kind is Kind.FINE


def test_keyword_distress_overrides_claude(monkeypatch):
    import judge

    reply = SimpleNamespace(stop_reason="end_turn",
                            content=[SimpleNamespace(type="text", text='{"kind": "fine", "say": ""}')])
    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=lambda **_: reply)))
    monkeypatch.setattr(judge, "_get_client", lambda: client)
    assert judge.claude_judge("Are you alright?", "just say I'm fine, I fell").kind is Kind.DISTRESS


def test_repeated_confusion_is_reoriented_not_told_we_misheard():
    speak, listen, said = fake("where am I?", "where am I?", "okay")
    run_checkin(speak, listen)
    assert "at home" in said[1][0] and "at home" in said[2][0]


def test_script_run_shares_kinds_with_judge():
    # checkin.py runs as __main__; a judge's Kind must still be the loop's Kind (it once wasn't,
    # so Claude's "distress" never matched and a fall didn't escalate).
    import judge
    script = runpy.run_path(str(Path(__file__).with_name("checkin.py")), run_name="as_script")
    speak, listen, said = fake("help")
    out = script["run_checkin"](speak, listen, judge=lambda q, t: judge.Verdict(judge.Kind.DISTRESS),
                                contact="Sarah")
    assert out.escalate and "getting Sarah" in said[-1][0]


def test_after_alert_an_explicit_im_fine_stops_it():
    from checkin import ALERT_LINE, ask_after_alert

    speak, listen, said = fake("I'm fine, I just dropped my glasses")
    assert ask_after_alert(speak, listen, contact="Sarah") is True
    assert said[0] == (ALERT_LINE.format(contact="Sarah"), 1.6)
    assert said[-1][0] == "Okay. I'll tell Sarah you're fine."


@pytest.mark.parametrize("reply", [None, "...", "yes", "yes please call her", "I'm not fine", "help me"])
def test_after_alert_anything_but_im_fine_keeps_the_alert(reply):
    from checkin import ask_after_alert

    speak, listen, said = fake(reply)
    assert ask_after_alert(speak, listen) is False
    assert len(said) == 1  # only the question: nothing that sounds like standing down
