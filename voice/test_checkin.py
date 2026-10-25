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
    assert out.escalate and out.distress and "fallen" in out.reason
    assert "getting Sarah" in said[-1][0] and len(said) == 2


def test_silence_two_louder_tries_then_warning_then_escalate():
    speak, listen, said = fake(None, None, None)
    out = run_checkin(speak, listen, contact="Sarah")
    assert out.escalate and not out.distress and out.reason == "She didn't answer."
    asks = [v for _, v in said[:2]]
    assert asks == sorted(asks) and asks[0] < asks[-1]
    assert "let Sarah know" in said[2][0] and len(said) == 3


def test_fine_during_warning_cancels():
    speak, listen, said = fake(None, None, "I'm fine, sorry")
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
    # first ask, then 2 tries after the reorient, the warning, then nothing more
    assert out.escalate and len(said) == 1 + 2 + 1 and "confused" in out.reason


def test_judge_wording_used_for_fine_but_not_distress():
    def judge(q, text):
        if "fallen" in text:
            return Verdict(Kind.DISTRESS, "a made-up distress line")
        return Verdict(Kind.FINE, "Lovely, take your time.")
    # long enough to go to the judge (a short "I'm good" stands down without it)
    speak, listen, said = fake("I'm good, I just needed some water and a little walk")
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
        speak, listen, _ = fake(None, None, reply)
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


def test_alert_asks_are_spaced_out_and_capped():
    from checkin import ALERT_ASK_EVERY_S, ALERT_ASKS_MAX

    assert ALERT_ASK_EVERY_S >= 60 and ALERT_ASKS_MAX * ALERT_ASK_EVERY_S <= 15 * 60


def test_the_warning_is_the_last_thing_she_hears():
    speak, listen, said = fake(None, None, None, None)
    out = run_checkin(speak, listen, contact="Sarah")
    assert out.escalate and "let Sarah know" in said[-1][0]


@pytest.mark.parametrize("reply,calls_now", [
    ("I'm hurt, please help", True),
    ("I've fallen and I can't get up", True),
    ("help me", True),
    ("please call Sarah for me", True),
    ("I didn't bleed properly", False),  # venue chatter Claude read as distress: gentle ladder
    ("I'm scared", False),
    ("I feel dizzy", True),
])
def test_only_an_explicit_call_for_help_phones_family_at_once(reply, calls_now):
    speak, listen, said = fake(reply)
    out = run_checkin(speak, listen, judge=lambda _q, _t: Verdict(Kind.DISTRESS))
    assert out.escalate and out.distress is calls_now
    assert out.reason == f'She said: "{reply}"'  # what the call tells family


@pytest.mark.parametrize("text", ["I don't need help", "no help needed, I'm fine", "I'm not hurt"])
def test_saying_no_help_is_not_asking_for_it(text):
    from judge import asked_for_help

    assert not asked_for_help(text)


@pytest.mark.parametrize("text", [
    "Help!", "help help", "please help", "help me", "help me up", "I need help", "can you help",
    "pillow, help", "get me help", "somebody send help", "can someone help me",
])
def test_help_asked_of_the_pillow_counts(text):
    from judge import asked_for_help

    assert asked_for_help(text)


@pytest.mark.parametrize("text", [
    "An agentic carer. Agentic help. Tutor.",  # venue chatter heard during a real check-in
    "Okay, can you like help me think?",
    "can you help me with the slides",
    "that really helps a lot, thanks",
    "the help desk said they would sort it out tomorrow",
])
def test_help_in_passing_chatter_does_not(text):
    from judge import asked_for_help

    assert not asked_for_help(text)


@pytest.mark.parametrize("reply", ["I'm fine.", "Yes, I'm fine.", "Yes.", "I'm okay, just the loo"])
def test_a_plain_im_fine_skips_the_judge(reply):
    def judge(_q, _t):
        raise AssertionError("the judge should not be asked")

    speak, listen, said = fake(reply)
    out = run_checkin(speak, listen, judge=judge)
    assert not out.escalate


@pytest.mark.parametrize("reply", ["I'm fine but I fell", "I'm not fine", "I'm fine, where am I?",
                                   "I'm okay I think but my chest hurts a bit",
                                   "No, why is this the last king? Yes.", "No, I'm fine", "Yes, okay, good, sure",
                                   "Good."])
def test_anything_hedged_or_alarming_still_goes_to_the_judge(reply):
    from judge import plainly_fine

    assert not plainly_fine(reply)


def test_the_outcome_is_reported_before_the_closing_line():
    events = []
    speak, listen, said = fake("I'm fine")

    def speak_logged(text, volume=1.0):
        events.append(("say", text))
        speak(text, volume=volume)

    out = run_checkin(speak_logged, listen, report=lambda o: events.append(("report", o.escalate)))
    assert not out.escalate
    assert events.index(("report", False)) < len(events) - 1  # reported, then the last line spoken
    assert events[-1][0] == "say"


def test_distress_is_reported_before_she_is_told_help_is_coming():
    events = []
    speak, listen, said = fake("I've fallen, I can't get up")

    def speak_logged(text, volume=1.0):
        events.append(("say", text))
        speak(text, volume=volume)

    out = run_checkin(speak_logged, listen, report=lambda o: events.append(("report", o.escalate)))
    assert out.escalate and out.distress
    assert events[-2] == ("report", True) and "Help is coming" in events[-1][1]


@pytest.mark.parametrize("reply", ["I'm feeling really dizzy.", "I'm extremely dizzy, I think I'm gonna throw up",
                                   "I feel faint", "I'm feeling really sick"])
def test_dizzy_or_faint_phones_family_at_once(reply):
    speak, listen, said = fake(reply)
    out = run_checkin(speak, listen)
    assert out.escalate and out.distress


def test_not_dizzy_is_not_a_call_for_help():
    from judge import asked_for_help

    assert not asked_for_help("I'm not dizzy, I'm fine") and not asked_for_help("I don't feel sick")


def test_demo_pace_asks_once_then_warns():
    from checkin import DEMO_PACE

    speak, listen, said = fake(None, None)
    out = run_checkin(speak, listen, **DEMO_PACE)
    assert out.escalate and len(said) == 2  # one ask, then the warning
