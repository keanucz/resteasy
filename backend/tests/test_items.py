"""Tests for the example items CRUD router."""

from fastapi.testclient import TestClient


def test_item_lifecycle(client: TestClient) -> None:
    """An item can be created, read, updated and deleted."""
    created = client.post("/api/items", json={"name": "Widget"})
    assert created.status_code == 201
    item_id = created.json()["id"]

    assert client.get(f"/api/items/{item_id}").json()["name"] == "Widget"

    updated = client.patch(f"/api/items/{item_id}", json={"description": "Shiny"})
    assert updated.json() == {"id": item_id, "name": "Widget", "description": "Shiny"}

    assert client.delete(f"/api/items/{item_id}").status_code == 204
    assert client.get(f"/api/items/{item_id}").status_code == 404


def test_create_item_rejects_empty_name(client: TestClient) -> None:
    """Validation rejects an empty name."""
    assert client.post("/api/items", json={"name": ""}).status_code == 422
