"""FastAPI dependencies shared across routers."""

import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from supabase import AsyncClient

from app.agents.watch_service import WatchService
from app.core.app_constants import CHECKIN_TOKEN_NOT_CONFIGURED, SUPABASE_NOT_CONFIGURED
from app.core.config import get_settings
from app.crud.pillows import get_pillow
from app.schemas.pillow import Pillow


def get_supabase(request: Request) -> AsyncClient:
    """Return the process-wide Supabase client, or 503 when the backend has no credentials."""
    client = request.app.state.supabase
    if client is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=SUPABASE_NOT_CONFIGURED)
    return client


SupabaseDep = Annotated[AsyncClient, Depends(get_supabase)]


async def existing_pillow(pillow_id: str, db: SupabaseDep) -> Pillow:
    """Resolve the `pillow_id` path parameter to a registered pillow, or 404."""
    pillow = await get_pillow(db, pillow_id)
    if pillow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Pillow {pillow_id} not found")
    return pillow


PillowDep = Annotated[Pillow, Depends(existing_pillow)]


def get_night_watch(request: Request) -> WatchService:
    """Return the process-wide Night Watch service (one watch per pillow)."""
    return request.app.state.night_watch


NightWatchDep = Annotated[WatchService, Depends(get_night_watch)]


def require_checkin_token(authorization: Annotated[str | None, Header()] = None) -> None:
    """Only the base laptop may report a check-in result (it can cancel or start an escalation)."""
    expected = get_settings().checkin_token
    if not expected:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=CHECKIN_TOKEN_NOT_CONFIGURED)
    if not secrets.compare_digest((authorization or "").encode(), f"Bearer {expected}".encode()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid check-in token",
                            headers={"WWW-Authenticate": "Bearer"})
