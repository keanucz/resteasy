"""Tests for the health router."""

from fastapi.testclient import TestClient


def test_hello(client: TestClient) -> None:
    """Root endpoint says hello."""
    response = client.get("/api/")
    assert response.status_code == 200
    assert response.json() == {"message": "Hello World"}


def test_health(client: TestClient) -> None:
    """Health endpoint reports ok."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
