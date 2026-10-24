"""FastAPI dependencies shared across routers."""

import secrets
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, UploadFile, status
from supabase import AsyncClient
from supabase_auth.errors import AuthError

from app.agents.reminders import ReminderService
from app.agents.watch_service import WatchService
from app.core.app_constants import (
    CHECKIN_TOKEN_NOT_CONFIGURED,
    NOT_LINKED,
    NOT_OWNER,
    NOT_SIGNED_IN,
    OWNER_ROLE,
    PHOTO_CONTENT_TYPES,
    PHOTO_EMPTY,
    PHOTO_MAX_BYTES,
    PHOTO_TOO_LARGE,
    PHOTO_WRONG_TYPE,
    SUPABASE_NOT_CONFIGURED,
)
from app.core.config import get_settings
from app.crud.accounts import get_role_for_user
from app.crud.pillows import get_pillow
from app.crud.residents import get_resident
from app.schemas.pillow import Pillow
from app.schemas.resident_photo import PhotoUpload


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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid check-in token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def current_user_id(db: SupabaseDep, authorization: Annotated[str | None, Header()] = None) -> str:
    """The Supabase Auth user behind the app's `Authorization: Bearer <access token>`, or 401."""
    token = (authorization or "").removeprefix("Bearer ").strip()
    try:
        response = await db.auth.get_user(token) if token else None
    except AuthError:  # expired, revoked or forged token
        response = None
    if response is None or response.user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail=NOT_SIGNED_IN, headers={"WWW-Authenticate": "Bearer"}
        )
    return response.user.id


UserIdDep = Annotated[str, Depends(current_user_id)]


async def require_role(db: AsyncClient, user_id: str, resident_id: str, *, owner: bool) -> None:
    """403 unless the login's contact looks after this resident (as the owner, when `owner`)."""
    role = await get_role_for_user(db, user_id, resident_id)
    if role is None or (owner and role != OWNER_ROLE):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_OWNER if role else NOT_LINKED)


async def existing_resident(resident_id: UUID, db: SupabaseDep) -> dict[str, Any]:
    """Resolve the `resident_id` path parameter to the resident's row, or 404."""
    resident = await get_resident(db, str(resident_id))
    if resident is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Resident {resident_id} not found")
    return resident


async def viewed_resident(
    user_id: UserIdDep, resident: Annotated[dict[str, Any], Depends(existing_resident)], db: SupabaseDep
) -> dict[str, Any]:
    """The resident in the path, for a login that looks after them (owner or contact)."""
    await require_role(db, user_id, resident["id"], owner=False)
    return resident


async def owned_resident(
    user_id: UserIdDep, resident: Annotated[dict[str, Any], Depends(existing_resident)], db: SupabaseDep
) -> dict[str, Any]:
    """The resident in the path, for the login of their owner only."""
    await require_role(db, user_id, resident["id"], owner=True)
    return resident


ViewedResidentDep = Annotated[dict[str, Any], Depends(viewed_resident)]
OwnedResidentDep = Annotated[dict[str, Any], Depends(owned_resident)]


async def photo_upload(file: UploadFile) -> PhotoUpload:
    """The multipart `file` as a photo: a JPEG, PNG or WebP (422 otherwise), at most 5 MB (413)."""
    if file.content_type not in PHOTO_CONTENT_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=PHOTO_WRONG_TYPE)
    content = await file.read(PHOTO_MAX_BYTES + 1)
    if not content:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=PHOTO_EMPTY)
    if len(content) > PHOTO_MAX_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail=PHOTO_TOO_LARGE)
    return PhotoUpload(content=content, content_type=file.content_type)


PhotoUploadDep = Annotated[PhotoUpload, Depends(photo_upload)]
