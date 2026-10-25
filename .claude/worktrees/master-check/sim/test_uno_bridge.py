"""Server command -> the line the pillow node reads on USB.  uv run --with pytest --with pyserial pytest sim/test_uno_bridge.py"""

from uno_bridge import command_to_line


def test_buzz_becomes_the_nodes_buzz_line():
    cmd = {"id": 41, "cmd": "buzz", "args": {"pattern": "chime", "repeat": 2}}
    assert command_to_line(cmd) == "BUZZ chime 2"


def test_buzz_without_repeat_plays_once():
    assert command_to_line({"id": 1, "cmd": "buzz", "args": {"pattern": "alert"}}) == "BUZZ alert 1"


def test_commands_the_node_cannot_run_give_no_line():
    assert command_to_line({"id": 2, "cmd": "set_light", "args": {"brightness_pct": 20}}) is None
    assert command_to_line({"id": 3, "cmd": "stop_all", "args": {}}) is None


def test_newest_state_keeps_only_the_last_state_line_and_echoes_the_rest():
    from uno_bridge import newest_state
    lines = [
        'UNO {"head_on":0,"fine":0,"talk":0,"family":0}',
        "radio: paired, rssi -50 dBm",
        'UNO {"head_on":1,"fine":0,"talk":0,"family":0}',
    ]
    state, others = newest_state(lines, pillow_id="test-pillow", ts=5.0)
    assert state["head_on"] is True and state["ts"] == 5.0
    assert others == ["radio: paired, rssi -50 dBm"]


def test_newest_state_with_no_state_line_is_none():
    from uno_bridge import newest_state
    assert newest_state(["buzz: alert x1"], pillow_id="test-pillow", ts=1.0) == (None, ["buzz: alert x1"])


def test_newest_id_is_where_polling_starts_so_a_restart_does_not_replay_old_commands():
    from uno_bridge import newest_id
    assert newest_id([{"id": 3, "cmd": "buzz"}, {"id": 7, "cmd": "buzz"}]) == 7
    assert newest_id([]) == 0
