"""FastAPI dependencies shared across routers."""

import secrets
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, Request, status
from supabase import AsyncClient

from app.agents.reminders import ReminderService
from app.agents.watch_service import WatchService
from app.core.app_constants import CHECKIN_TOKEN_NOT_CONFIGURED, SUPABASE_NOT_CONFIGURED
from app.core.config import get_settings
from app.crud.pillows import get_pillow
from app.crud.residents import get_resident
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


async def resident_of(db: AsyncClient, pillow: Pillow) -> dict[str, Any]:
    """The resident `pillow` belongs to (their row), or 404 when it has none."""
    resident = await get_resident(db, str(pillow.resident_id)) if pillow.resident_id else None
    if resident is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Pillow {pillow.id} has no resident")
    return resident


async def pillow_resident(pillow: PillowDep, db: SupabaseDep) -> dict[str, Any]:
    return await resident_of(db, pillow)


ResidentDep = Annotated[dict[str, Any], Depends(pillow_resident)]


def get_night_watch(request: Request) -> WatchService:
    """Return the process-wide Night Watch service (one watch per pillow)."""
    return request.app.state.night_watch


NightWatchDep = Annotated[WatchService, Depends(get_night_watch)]


def get_reminders(request: Request) -> ReminderService:
    """Return the process-wide reminder service (the Routine agent)."""
    return request.app.state.reminders


ReminderServiceDep = Annotated[ReminderService, Depends(get_reminders)]


def require_checkin_token(authorization: Annotated[str | None, Header()] = None) -> None:
    """Only the base laptop may report a check-in result (it can cancel or start an escalation)."""
    expected = get_settings().checkin_token
    if not expected:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=CHECKIN_TOKEN_NOT_CONFIGURED)
    if not secrets.compare_digest((authorization or "").encode(), f"Bearer {expected}".encode()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid check-in token",
                            headers={"WWW-Authenticate": "Bearer"})
