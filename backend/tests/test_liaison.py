"""Family Liaison: Claude words the family messages and the spoken line with tools; the ladder
(who, which channel, when) stays plain code, and anything Claude doesn't word keeps the fixed text."""

import asyncio
from types import SimpleNamespace

from app.agents.liaison import SEND_TOOL, SPEAK_TOOL, Liaison, Situation, apply_tool_calls
from app.agents.night_watch import Alert, Say

FACTS = "Margaret got up at 03:10 and hasn't come back to bed (25 min). She didn't answer."
PLANNED = [Alert("Sarah", "app", FACTS), Alert("Tom", "app", FACTS)]
SITUATION = Situation(resident="Margaret", alerts=PLANNED, events=["bed_exit", "no_return", "checkin_result"],
                      heard=["mmm... where..."])


def tool_use(name, **kwargs):
    return SimpleNamespace(type="tool_use", name=name, input=kwargs)


class FakeClaude:
    """Stands in for AsyncAnthropic: returns the given content blocks, or raises."""

    def __init__(self, content=None, error=None):
        self.calls = []
        self._content, self._error = content or [], error
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        return SimpleNamespace(stop_reason="tool_use", content=self._content)


def run(coro):
    return asyncio.run(coro)


def test_apply_uses_claude_wording_for_planned_alerts_only():
    calls = [
        tool_use(SEND_TOOL, contact="Sarah", channel="app", message="Mum's up 25 min, didn't answer."),
        tool_use(SEND_TOOL, contact="Nobody", channel="app", message="ignored"),
        tool_use(SEND_TOOL, contact="Tom", channel="call", message="wrong channel, ignored"),
    ]
    out = apply_tool_calls(PLANNED, calls)
    assert out == [Alert("Sarah", "app", "Mum's up 25 min, didn't answer."), PLANNED[1]]


def test_apply_keeps_one_spoken_line():
    calls = [tool_use(SPEAK_TOOL, text="Sarah knows. Stay where you are."),
             tool_use(SPEAK_TOOL, text="second")]
    out = apply_tool_calls(PLANNED, calls)
    assert out == [*PLANNED, Say("Sarah knows. Stay where you are.")]


def test_apply_drops_blank_wording():
    out = apply_tool_calls(PLANNED, [tool_use(SEND_TOOL, contact="Sarah", channel="app", message="   ")])
    assert out == PLANNED


def test_no_client_means_the_fixed_messages():
    liaison = Liaison(client=None)
    assert run(liaison.compose(SITUATION)) == PLANNED


def test_claude_rewords_and_speaks():
    fake = FakeClaude([
        tool_use(SEND_TOOL, contact="Sarah", channel="app", message="Mum got up at 03:10 and didn't answer."),
        tool_use(SEND_TOOL, contact="Tom", channel="app", message="Margaret has been up 25 min, no answer."),
        tool_use(SPEAK_TOOL, text="I've let Sarah and Tom know. Stay put, help is coming."),
    ])
    out = run(Liaison(client=fake).compose(SITUATION))
    assert [a.contact for a in out if isinstance(a, Alert)] == ["Sarah", "Tom"]
    assert out[0].message.startswith("Mum got up at 03:10")
    assert isinstance(out[-1], Say)
    (call,) = fake.calls
    assert call["model"] == "claude-opus-5-5"
    assert {t["name"] for t in call["tools"]} == {SEND_TOOL, SPEAK_TOOL}
    assert all(t["strict"] for t in call["tools"])
    assert call["tool_choice"] == {"type": "auto"}
    prompt = call["messages"][0]["content"]
    assert "Sarah" in prompt and "Tom" in prompt and "mmm... where..." in prompt and "no_return" in prompt


def test_a_failing_claude_falls_back_to_the_fixed_messages():
    out = run(Liaison(client=FakeClaude(error=RuntimeError("down"))).compose(SITUATION))
    assert out == PLANNED


def test_a_slow_claude_falls_back():
    class Slow(FakeClaude):
        async def _create(self, **kwargs):
            await asyncio.sleep(0.2)
            return await super()._create(**kwargs)

    out = run(Liaison(client=Slow(), timeout_s=0.01).compose(SITUATION))
    assert out == PLANNED


def test_nothing_to_send_makes_no_call():
    fake = FakeClaude()
    assert run(Liaison(client=fake).compose(Situation("Margaret", [], [], []))) == []
    assert fake.calls == []
