"""Shared pytest fixtures."""

import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from supabase import Client, create_client
from supabase_auth.errors import AuthApiError

from app.core.config import get_settings
from app.core.dependencies import get_supabase
from app.crud.crud_constants import (
    COMMANDS_TABLE,
    CONTACTS_TABLE,
    READINGS_TABLE,
    RESIDENT_CONTACTS_TABLE,
    RESIDENTS_TABLE,
)
from app.main import app
from tests.seed_constants import TEST_HELPER_PRIORITY, TEST_PILLOW_ID, TEST_RESIDENT_ID, TEST_USER_ID

# The test resident's settings the app tests may change, put back after each test
RESTORED_RESIDENT_KEYS = ("voice_id", "quiet_start", "quiet_end", "checkin_timeout_min", "monitoring_paused")


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
    """Yield a test client backed by the live Supabase project, clearing the test pillow's queue and
    sensor history after."""
    yield client
    for table in (COMMANDS_TABLE, READINGS_TABLE):
        db.table(table).delete().eq("pillow_id", TEST_PILLOW_ID).execute()


class _RejectingAuth:
    """Stands in for Supabase Auth when every token is expired or forged."""

    async def get_user(self, jwt: str) -> None:
        raise AuthApiError("invalid JWT", 401, "bad_jwt")


@pytest.fixture
def offline_client(client: TestClient) -> TestClient:
    """A test client whose Supabase rejects every login, for the 401 checks."""
    app.dependency_overrides[get_supabase] = lambda: SimpleNamespace(auth=_RejectingAuth())
    return client


@contextmanager
def _throwaway_login(db: Client) -> Iterator[tuple[str, str]]:
    """A confirmed Supabase Auth user, as (user id, access token); deleted afterwards.

    It signs in on a client of its own, so `db` keeps the secret key for setup and cleanup."""
    settings = get_settings()
    email, password = f"account-test-{secrets.token_hex(4)}@pillow.test", secrets.token_urlsafe(16)
    user = db.auth.admin.create_user({"email": email, "password": password, "email_confirm": True}).user
    try:
        auth = create_client(settings.supabase_url, settings.supabase_secret_key).auth
        yield user.id, auth.sign_in_with_password({"email": email, "password": password}).session.access_token
    finally:
        db.auth.admin.delete_user(user.id)


@pytest.fixture
def owner_token(db: Client) -> Iterator[str]:
    """A throwaway login linked to the test resident's owner; her settings are put back afterwards."""
    contact = db.table(CONTACTS_TABLE).select("user_id").eq("id", TEST_USER_ID).single().execute().data
    resident = db.table(RESIDENTS_TABLE).select("*").eq("id", TEST_RESIDENT_ID).single().execute().data
    with _throwaway_login(db) as (user_id, token):
        db.table(CONTACTS_TABLE).update({"user_id": user_id}).eq("id", TEST_USER_ID).execute()
        try:
            yield token
        finally:
            db.table(CONTACTS_TABLE).update({"user_id": contact["user_id"]}).eq("id", TEST_USER_ID).execute()
            restore = {key: resident[key] for key in RESTORED_RESIDENT_KEYS}
            db.table(RESIDENTS_TABLE).update(restore).eq("id", TEST_RESIDENT_ID).execute()


@pytest.fixture
def contact_token(db: Client) -> Iterator[str]:
    """A throwaway login linked to the test resident as a plain contact, not the owner."""
    with _throwaway_login(db) as (user_id, token):
        contact = db.table(CONTACTS_TABLE).insert({"full_name": "Test Helper", "user_id": user_id}).execute()
        contact_id = contact.data[0]["id"]
        link = {
            "resident_id": TEST_RESIDENT_ID,
            "contact_id": contact_id,
            "priority": TEST_HELPER_PRIORITY,
            "role": "contact",  # not the owner (the column defaults to owner for the demo)
        }
        try:
            db.table(RESIDENT_CONTACTS_TABLE).insert(link).execute()
            yield token
        finally:
            db.table(CONTACTS_TABLE).delete().eq("id", contact_id).execute()  # cascades to the link


@pytest.fixture
def stranger_token(db: Client) -> Iterator[str]:
    """A throwaway login linked to no one."""
    with _throwaway_login(db) as (_, token):
        yield token
