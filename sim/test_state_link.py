"""Which link the voice unit is on goes up as state.link.
uv run --with pytest --with bleak --with numpy --with pyserial pytest sim/test_state_link.py"""

import queue

from audio_bridge import BleBoard, FailoverBoard, HotspotBoard, SerialBoard, StatePoster

UNO = 'UNO {"head_on":1,"fine":0,"talk":0,"family":0}'


class _Poster(StatePoster):
    def __init__(self) -> None:  # no worker thread, no network
        self.pillow_id, self.imu_motion, self.imu_at = "test-pillow", None, 0.0
        self.latest = queue.Queue(maxsize=1)


def test_each_link_names_itself():
    assert SerialBoard("/dev/null", 115200).link == "usb"
    assert HotspotBoard("127.0.0.1", 0).link == "hotspot"
    assert BleBoard("pillow").link == "ble"


def test_a_state_line_carries_the_link_it_came_over():
    board = HotspotBoard("127.0.0.1", 0)
    board.poster = _Poster()
    board._line(UNO)
    assert board.poster.latest.get_nowait()["link"] == "hotspot"


def test_posting_without_a_link_leaves_it_out():
    poster = _Poster()
    assert poster.post(UNO)
    assert "link" not in poster.latest.get_nowait()


def test_with_failover_only_the_active_link_posts(monkeypatch):
    hot, ble = HotspotBoard("127.0.0.1", 0), BleBoard("pillow")
    monkeypatch.setattr(hot, "connected", lambda: True)
    monkeypatch.setattr(ble, "connected", lambda: True)
    board = FailoverBoard([hot, ble])
    board.poster = _Poster()
    ble._line(UNO)  # a late line from the link on its way out
    assert board.poster.latest.empty()
    hot._line(UNO)
    assert board.poster.latest.get_nowait()["link"] == "hotspot"



def test_usb_comes_first_then_the_hotspot_then_bluetooth():
    usb, hot, ble = SerialBoard("/dev/null", 115200), HotspotBoard("127.0.0.1", 0), BleBoard("pillow")
    board = FailoverBoard([usb, hot, ble])
    assert board.active() is None
    hot.port = object()  # on the hotspot
    assert board.active() is hot
    assert ble.standby()  # Bluetooth stays off while a better link is up
    usb.port = object()  # cable plugged in: it wins even with the hotspot up
    assert board.active() is usb
    usb.port = None  # unplugged
    assert board.active() is hot
    hot.port = None  # and the hotspot drops
    assert board.active() is None
    assert not ble.standby()  # so Bluetooth may connect
