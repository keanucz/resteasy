"""Saying a due reminder against scripted replies, no audio.  uv run --with pytest pytest voice"""

from types import SimpleNamespace

import pytest
from checkin_client import REMINDER_CHECK_S, reminders_due
from judge import Answer, keyword_reminder_judge
from reminder import ASK, run_reminder

LINE = "Margaret, it's time to take your heart tablets."


def fake(reply=None):
    """speak/listen pair; `reply` None = silence, "..." = a mumble."""
    said, heard = [], []

    def speak(text, volume=1.0):
        said.append(text)

    def listen(no_answer_s):
        heard.append(no_answer_s)
        if reply is None:
            return SimpleNamespace(text="", spoke=False)
        return SimpleNamespace(text="" if reply == "..." else reply, spoke=True)

    return speak, listen, said, heard


def run(reply=None, confirm=True, **kw):
    speak, listen, said, heard = fake(reply)
    out = run_reminder(speak, listen, text=LINE, confirm=confirm, sleep=lambda _: None, **kw)
    return out, said, heard


def test_announce_only_says_one_line_and_never_listens():
    out, said, heard = run(confirm=False)
    assert (out.outcome, said, heard) == ("announced", [LINE], [])


def test_confirmed():
    out, said, _ = run("Yes, I had them with breakfast")
    assert said[0] == f"{LINE} {ASK}"
    assert (out.outcome, out.reply) == ("done", "Yes, I had them with breakfast")


@pytest.mark.parametrize(("reply", "outcome"), [
    ("Not yet, I'll do it after my tea", "not_done"),
    ("hmm what", "not_done"),  # couldn't tell: asked again later
    ("...", "not_done"),
    (None, "no_answer"),
    ("I've fallen and I can't get up", "distress"),
    ("No, I don't feel well", "distress"),
])
def test_outcomes(reply, outcome):
    assert run(reply)[0].outcome == outcome


def test_distress_is_told_help_is_coming():
    _, said, _ = run("help")
    assert "Help is coming" in said[-1]


def test_a_broken_speaker_or_judge_means_ask_again_later():
    def boom(*_a, **_k):
        raise RuntimeError("no audio device")

    out = run_reminder(boom, boom, text=LINE, confirm=True, sleep=lambda _: None)
    assert out.outcome == "no_answer"
    out, _, _ = run("yes", judge=boom)
    assert out.outcome == "no_answer"


def test_keyword_judge():
    assert keyword_reminder_judge(LINE, "yep, done") is Answer.DONE
    assert keyword_reminder_judge(LINE, "I forgot") is Answer.NOT_YET
    assert keyword_reminder_judge(LINE, "my chest hurts") is Answer.DISTRESS


def test_reminders_are_checked_only_by_day_and_not_every_poll():
    assert reminders_due("awake", 100.0, 0.0)
    assert not reminders_due("awake", REMINDER_CHECK_S - 1, 0.0)
    for night in ("in_bed", "up", "check_in", "escalating", None):
        assert not reminders_due(night, 100.0, 0.0)
