"""Public images: the Fetch.ai agents' Agentverse avatars."""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize("name", ["coordinator", "sarah", "szymon", "family"])
def test_agent_avatars_are_served(client: TestClient, name: str) -> None:
    response = client.get(f"/static/agents/{name}.png")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"


def test_unknown_static_file_is_404(client: TestClient) -> None:
    assert client.get("/static/agents/nobody.png").status_code == 404
