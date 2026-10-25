"""audio_bridge.buzz_line: server `buzz` args -> the voice unit's BUZZ command."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audio_bridge import buzz_line


def test_chime_and_alert() -> None:
    assert buzz_line({"pattern": "chime", "repeat": 2}) == "BUZZ chime 2"
    assert buzz_line({"pattern": "alert"}) == "BUZZ alert 1"


def test_repeat_clamped() -> None:
    assert buzz_line({"pattern": "chime", "repeat": 9}) == "BUZZ chime 3"
    assert buzz_line({"pattern": "chime", "repeat": 0}) == "BUZZ chime 1"
    assert buzz_line({"pattern": "chime", "repeat": "x"}) == "BUZZ chime 1"


def test_rejects_unknown() -> None:
    assert buzz_line({"pattern": "siren"}) is None
    assert buzz_line("chime") is None
    assert buzz_line(None) is None
