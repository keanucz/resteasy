"""Shared pytest fixtures."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Yield a test client for the app with dependency overrides reset afterwards."""
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
