"""Shared pytest fixtures."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from supabase import Client, create_client

from app.core.config import get_settings
from app.crud.crud_constants import COMMANDS_TABLE
from app.main import app
from tests.seed_constants import TEST_PILLOW_ID


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Yield a test client for the app with dependency overrides reset afterwards."""
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(scope="session")
def db() -> Client:
    """Return a direct Supabase client for setup and cleanup, skipping when none is configured."""
    settings = get_settings()
    if not settings.supabase_configured:
        pytest.skip("SUPABASE_URL / SUPABASE_SECRET_KEY not set; live Supabase tests skipped")
    return create_client(settings.supabase_url, settings.supabase_secret_key)


@pytest.fixture
def live_client(db: Client, client: TestClient) -> Iterator[TestClient]:
    """Yield a test client backed by the live Supabase project, clearing the test pillow's queue after."""
    yield client
    db.table(COMMANDS_TABLE).delete().eq("pillow_id", TEST_PILLOW_ID).execute()
