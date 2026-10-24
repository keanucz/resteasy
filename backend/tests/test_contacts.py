"""Tests for the contact router against the seeded test user."""

from fastapi.testclient import TestClient

from tests.seed_constants import TEST_PILLOW_ID, TEST_USER_ID, UNKNOWN_CONTACT_ID


def test_test_user_sees_their_pillow(live_client: TestClient) -> None:
    """The test user owns the test resident, so their pillow list is exactly the test pillow."""
    response = live_client.get(f"/api/contacts/{TEST_USER_ID}/pillows")
    assert response.status_code == 200
    assert [pillow["id"] for pillow in response.json()] == [TEST_PILLOW_ID]


def test_contact_without_residents_sees_nothing(live_client: TestClient) -> None:
    """A contact who looks after nobody gets an empty list."""
    assert live_client.get(f"/api/contacts/{UNKNOWN_CONTACT_ID}/pillows").json() == []


def test_rejects_malformed_contact_id(live_client: TestClient) -> None:
    """Contact ids must be UUIDs."""
    assert live_client.get("/api/contacts/not-a-uuid/pillows").status_code == 422
