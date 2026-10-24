"""Helpers shared by every Supabase-backed CRUD module."""

from typing import Any


async def fetch_one(query: Any) -> dict[str, Any] | None:
    """Run a filtered select expected to match at most one row and return it, or None."""
    response = await query.maybe_single().execute()
    return response.data if response else None
