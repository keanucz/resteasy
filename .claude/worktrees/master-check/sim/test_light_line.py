"""audio_bridge.light_line: server `set_light` args -> the voice unit's LIGHT command."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audio_bridge import light_line


def test_path_light_on_and_off() -> None:
    assert light_line({"brightness_pct": 20, "color": "warm", "fade_s": 3}) == "LIGHT 20 warm 3"
    assert light_line({"brightness_pct": 0, "color": "off", "fade_s": 10}) == "LIGHT 0 off 10"
    assert light_line({"brightness_pct": 40, "color": "amber"}) == "LIGHT 40 amber 0"


def test_off_colour_means_dark() -> None:
    assert light_line({"brightness_pct": 50, "color": "off"}) == "LIGHT 0 off 0"


def test_ranges_clamped() -> None:
    assert light_line({"brightness_pct": 250, "color": "warm", "fade_s": 999}) == "LIGHT 100 warm 60"
    assert light_line({"brightness_pct": -5, "color": "warm", "fade_s": -1}) == "LIGHT 0 warm 0"
    assert light_line({"brightness_pct": "x", "color": "warm"}) == "LIGHT 0 warm 0"


def test_rejects_unknown() -> None:
    assert light_line({"brightness_pct": 20, "color": "purple"}) is None
    assert light_line("warm") is None
    assert light_line(None) is None
