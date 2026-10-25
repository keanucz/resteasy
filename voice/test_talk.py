"""Talking to the pillow against scripted replies: no audio, no Cartesia, no Claude.
uv run --with pytest --with numpy pytest voice"""

from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from judge import Confirm, keyword_confirm_judge
from talk import (
    ASK_CHANGE,
    GAVE_UP,
    GUARDIAN_NO,
    LISTENING,
    NOT_HEARD,
    NOT_UNDERSTOOD,
    Request,
    TalkSession,
    Voice,
    read_back,
    say_reminders,
    spoken_time,
    valid,
)

TZ = ZoneInfo("America/Los_Angeles")
TODAY = datetime.now(TZ).date()
TOMORROW = date.fromordinal(TODAY.toordinal() + 1)
TABLETS = Request("set_reminder", label="take your tablets", time_of_day="08:00",
                  on_date=TOMORROW.isoformat(), kind="meds")


class FakeEars:
    def __init__(self, heard: str) -> None:
        self.heard, self.opened, self.cancelled = heard, False, False
        self.live = SimpleNamespace(set=lambda: None)

    def open(self):
        self.opened = True

    def cancel(self):
        self.cancelled = True

    def result(self, timeout=60.0):
        return SimpleNamespace(text=self.heard, spoke=bool(self.heard))


class FakePillow:
    def __init__(self, guardian_no: bool = False, entries=None) -> None:
        self.saved, self.guardian_no, self.entries = [], guardian_no, entries or []

    def add_reminder(self, r):
        if self.guardian_no:
            return False, "label: dosing"
        self.saved.append(r)
        return True, None

    def calendar(self, start, end):
        return self.entries


def session(heard: str, answers: list[str], requests: list[Request], pillow=None):
    said, distress = [], []
    replies = iter(answers)
    intents = iter(requests)

    def listen(no_answer_s=8.0):
        text = next(replies, "")
        return SimpleNamespace(text=text, spoke=bool(text))

    v = Voice(say=said.append, beep=lambda: None, got_it=lambda: None, listen=listen,
              intent=lambda text, now: next(intents),
              confirm=keyword_confirm_judge, pillow=pillow or FakePillow(), on_distress=distress.append,
              log=lambda m: None)
    s = TalkSession(v, FakeEars(heard), TZ)
    return s, said, distress, v.pillow


def test_set_a_reminder_by_voice():
    s, said, distress, pillow = session("remind me to take my tablets tomorrow morning", ["yes please"], [TABLETS])
    s.arm()
    s.go()
    assert said[0] == LISTENING
    assert said[1] == "I'll remind you to take your tablets at 8 in the morning tomorrow. Is that right?"
    assert pillow.saved == [TABLETS]
    assert said[-1] == "Done. I'll remind you to take your tablets."
    assert not distress


def test_no_then_a_correction_is_read_back_again():
    nine = Request("set_reminder", label="take your tablets", time_of_day="09:00",
                   on_date=TOMORROW.isoformat(), kind="meds")
    s, said, _, pillow = session("remind me to take my tablets tomorrow morning",
                                 ["no", "make it nine", "yes"], [TABLETS, nine])
    s.go()
    assert "9 in the morning" in said[-2] and pillow.saved == [nine]


def test_a_no_with_the_change_in_it_skips_the_question():
    nine = Request("set_reminder", label="take your tablets", time_of_day="09:00",
                   on_date=TOMORROW.isoformat(), kind="meds")
    s, said, _, pillow = session("remind me tomorrow", ["no, make it nine", "yes"], [TABLETS, nine])
    s.go()
    assert ASK_CHANGE not in said and pillow.saved == [nine]


def test_two_noes_and_it_gives_up_without_saving():
    s, said, _, pillow = session("remind me tomorrow", ["no", "nine", "no"], [TABLETS, TABLETS])
    s.go()
    assert said[-1] == GAVE_UP and pillow.saved == []


def test_the_guardian_saying_no_is_explained_kindly():
    s, said, _, _ = session("remind me to take double my dose", ["yes"], [TABLETS], FakePillow(guardian_no=True))
    s.go()
    assert said[-1] == GUARDIAN_NO


def test_distress_starts_the_ladder_at_any_point():
    s, said, distress, pillow = session("help I've fallen", [], [])
    s.go()
    assert distress and pillow.saved == []
    s, said, distress, pillow = session("remind me tomorrow", ["I can't get up"], [TABLETS])
    s.go()
    assert distress and pillow.saved == []


def test_silence_and_nonsense():
    s, said, _, _ = session("", [], [])
    s.go()
    assert said == [LISTENING, NOT_HEARD]
    s, said, _, _ = session("what's the weather", [], [Request("unclear")])
    s.go()
    assert said[-1] == NOT_UNDERSTOOD


def test_list_reminders():
    entries = [{"due_at": f"{TOMORROW.isoformat()}T16:00:00+00:00", "label": "call Sarah"},
               {"due_at": f"{TOMORROW.isoformat()}T15:00:00+00:00", "label": "take your heart tablets"}]
    ask = Request("list_reminders", start=TOMORROW.isoformat(), end=TOMORROW.isoformat())
    s, said, _, _ = session("what have I got tomorrow", [], [ask], FakePillow(entries=entries))
    s.go()
    assert said[-1] == ("Tomorrow: take your heart tablets at 8 in the morning, "
                        "and call Sarah at 9 in the morning.")
    assert say_reminders([], TOMORROW, TOMORROW, TODAY, TZ) == "You don't have any reminders tomorrow."


def test_short_press_cancels():
    s, said, _, _ = session("x", [], [])
    s.arm()
    s.cancel()
    assert s.ears.cancelled and said == []


def test_spoken_words():
    assert spoken_time("08:00") == "8 in the morning"
    assert spoken_time("19:30") == "7:30 in the evening"
    assert spoken_time("12:00") == "midday"
    weekly = Request("set_reminder", label="call Sarah", time_of_day="18:00", days=(1, 3))
    assert read_back(weekly, TODAY) == ("I'll remind you to call Sarah at 6 in the evening every Monday and "
                                        "Wednesday. Is that right?")


def test_validation_of_what_claude_returns():
    assert valid(TABLETS)
    assert not valid(Request("set_reminder", label="x", time_of_day="8am", on_date=TODAY.isoformat()))
    assert not valid(Request("set_reminder", label="x", time_of_day="08:00"))  # no day at all
    assert not valid(Request("list_reminders", start="2026-10-26", end="2026-10-25"))


def test_confirm_keywords():
    assert keyword_confirm_judge("", "yes that's right") is Confirm.YES
    assert keyword_confirm_judge("", "no, nine o'clock") is Confirm.NO
    assert keyword_confirm_judge("", "help me") is Confirm.DISTRESS
    assert keyword_confirm_judge("", "hmm") is Confirm.UNCLEAR


def test_the_fine_key_stops_a_check_in_before_the_next_question():
    from checkin import STOPPED_REASON, run_checkin

    said = []
    out = run_checkin(lambda t, volume=1.0: said.append(t), lambda no_answer_s: SimpleNamespace(text="", spoke=False),
                      should_stop=lambda: True)
    assert (out.escalate, out.reason) == (False, STOPPED_REASON)
    assert said == ["Okay. Glad you're okay."]
