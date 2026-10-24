"""Tests for the pillow router against the seeded test pillow."""

import pytest
from fastapi.testclient import TestClient

from tests.seed_constants import TEST_PILLOW_ID, TEST_RESIDENT_ID, UNKNOWN_PILLOW_ID

DEVICE_STATE = {
    "pillow_id": TEST_PILLOW_ID,
    "ts": 1792815000.25,
    "head_on": True,
    "motion": 0.12,
    "room_motion": False,
    "light": 0.03,
    "temp_c": 19.5,
    "humidity": 48,
    "keys": {"talk": False, "fine": True, "family": False},
    "knob": 5,
}


def test_read_pillow(live_client: TestClient) -> None:
    """The test pillow is registered to the test resident."""
    response = live_client.get(f"/api/pillows/{TEST_PILLOW_ID}")
    assert response.status_code == 200
    assert response.json()["resident_id"] == TEST_RESIDENT_ID


def test_unknown_pillow_is_404(live_client: TestClient) -> None:
    """Every pillow route rejects an unregistered pillow id."""
    assert live_client.get(f"/api/pillows/{UNKNOWN_PILLOW_ID}").status_code == 404
    assert live_client.post(f"/api/pillows/{UNKNOWN_PILLOW_ID}/state", json=DEVICE_STATE).status_code == 404


def test_state_round_trip(live_client: TestClient) -> None:
    """A device report is stored, flattened, and read back by the app."""
    posted = live_client.post(f"/api/pillows/{TEST_PILLOW_ID}/state", json=DEVICE_STATE)
    assert posted.status_code == 200

    stored = live_client.get(f"/api/pillows/{TEST_PILLOW_ID}/state").json()
    assert stored["head_on"] is True
    assert stored["key_fine"] is True
    assert stored["knob"] == 5
    assert stored["device_ts"].startswith("2026-10-24")
    assert stored["night_state"]


def test_state_accepts_unwired_sensors(live_client: TestClient) -> None:
    """Sensors that are not wired arrive as null and are stored as null."""
    unwired = {**DEVICE_STATE, "temp_c": None, "humidity": None, "knob": None}
    assert live_client.post(f"/api/pillows/{TEST_PILLOW_ID}/state", json=unwired).status_code == 200
    assert live_client.get(f"/api/pillows/{TEST_PILLOW_ID}/state").json()["temp_c"] is None


@pytest.mark.parametrize("field, value", [("motion", 1.5), ("knob", 11), ("humidity", -1)])
def test_state_rejects_out_of_range(live_client: TestClient, field: str, value: float) -> None:
    """Readings outside the contract's ranges are rejected before reaching the database."""
    response = live_client.post(f"/api/pillows/{TEST_PILLOW_ID}/state", json={**DEVICE_STATE, field: value})
    assert response.status_code == 422


def test_missing_supabase_is_503(client: TestClient) -> None:
    """Database routes answer 503 instead of crashing when the server has no Supabase credentials."""
    client.app.state.supabase = None
    assert client.get(f"/api/pillows/{TEST_PILLOW_ID}").status_code == 503
