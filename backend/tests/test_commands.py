"""Tests for the command router against the seeded test pillow."""

from fastapi.testclient import TestClient

from tests.seed_constants import TEST_PILLOW_ID, UNKNOWN_PILLOW_ID

COMMANDS_URL = f"/api/pillows/{TEST_PILLOW_ID}/commands"
SET_LIGHT = {
    "cmd": "set_light",
    "args": {"brightness_pct": 20, "color": "warm", "fade_s": 3},
    "source": "tests",
}


def test_queue_and_poll(live_client: TestClient) -> None:
    """A queued command comes back to the polling device in the contract shape, oldest first."""
    first = live_client.post(COMMANDS_URL, json=SET_LIGHT)
    assert first.status_code == 201
    second = live_client.post(COMMANDS_URL, json={"cmd": "stop_all"})
    first_id = first.json()["id"]

    polled = live_client.get(COMMANDS_URL, params={"after": first_id - 1}).json()
    assert polled == [
        {"id": first_id, "cmd": "set_light", "args": SET_LIGHT["args"]},
        {"id": second.json()["id"], "cmd": "stop_all", "args": {}},
    ]


def test_poll_after_last_id_is_empty(live_client: TestClient) -> None:
    """Once the device has seen a command id, polling after it returns nothing new."""
    last_id = live_client.post(COMMANDS_URL, json=SET_LIGHT).json()["id"]
    assert live_client.get(COMMANDS_URL, params={"after": last_id}).json() == []


def test_rejects_unknown_command(live_client: TestClient) -> None:
    """Only commands the device understands can be queued."""
    assert live_client.post(COMMANDS_URL, json={"cmd": "explode"}).status_code == 422


def test_unknown_pillow_is_404(live_client: TestClient) -> None:
    """Commands cannot be queued for or polled by an unregistered pillow."""
    assert live_client.get(f"/api/pillows/{UNKNOWN_PILLOW_ID}/commands").status_code == 404
    assert live_client.post(f"/api/pillows/{UNKNOWN_PILLOW_ID}/commands", json=SET_LIGHT).status_code == 404
