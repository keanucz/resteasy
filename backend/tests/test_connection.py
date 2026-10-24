"""Tests for the connection-test router."""

from fastapi.testclient import TestClient


def test_connection_test_echoes_host(client: TestClient) -> None:
    """The test endpoint confirms the request and reports the host it was sent to."""
    response = client.get("/api/test", headers={"host": "example.trycloudflare.com"})
    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Frontend reached the backend"
    assert body["host"] == "example.trycloudflare.com"
    assert body["server_time"]
