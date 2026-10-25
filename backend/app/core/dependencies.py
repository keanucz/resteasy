"""FastAPI dependencies shared across routers."""

import secrets
from dataclasses import dataclass
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import Depends, Form, Header, HTTPException, Query, Request, UploadFile, status
from supabase import AsyncClient
from supabase_auth.errors import AuthError

from app.agents.reminders import ReminderService
from app.agents.watch_service import WatchService
from app.core.app_constants import (
    AGENT_CONTACT_MISMATCH,
    AGENT_CONTACT_MISSING,
    AGENT_CONTACT_NOT_LINKED,
    AGENT_OWN_TOKEN,
    AS_RESIDENT,
    CHECKIN_TOKEN_NOT_CONFIGURED,
    FAMILY_AGENT,
    NOT_AN_AGENT,
    NOT_LINKED,
    NOT_OWNER,
    NOT_SIGNED_IN,
    OWNER_ROLE,
    PHOTO_CONTENT_TYPES,
    PHOTO_EMPTY,
    PHOTO_MAX_BYTES,
    PHOTO_TOO_LARGE,
    PHOTO_WRONG_TYPE,
    PILLOW_VOICE_AGENT,
    SUPABASE_NOT_CONFIGURED,
)
from app.core.config import get_settings
from app.core.voice_constants import (
    CLIP_CONTENT_TYPES,
    CLIP_EMPTY,
    CLIP_MAX_BYTES,
    CLIP_TOO_LARGE,
    CLIP_WRONG_TYPE,
    CLONE_NAME_MAX,
    CLONE_NAME_MISSING,
    CONSENT_GIVEN,
    CONSENT_MISSING,
    VOICE_NOT_CONFIGURED,
)
from app.crud.accounts import get_link_for_contact, get_link_for_user
from app.crud.pillows import get_pillow
from app.crud.residents import get_resident
from app.schemas.pillow import Pillow
from app.schemas.resident_photo import PhotoUpload
from app.schemas.voice import CloneUpload
from app.sensors.readings_recorder import ReadingsRecorder
from app.voice.cartesia import Cartesia


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


def get_readings_recorder(request: Request) -> ReadingsRecorder:
    """Return the process-wide recorder that turns state reports into per-minute readings."""
    return request.app.state.readings


ReadingsRecorderDep = Annotated[ReadingsRecorder, Depends(get_readings_recorder)]


def get_reminders(request: Request) -> ReminderService:
    """Return the process-wide reminder service (the Routine agent)."""
    return request.app.state.reminders


ReminderServiceDep = Annotated[ReminderService, Depends(get_reminders)]


def _is_checkin_token(authorization: str | None, expected: str) -> bool:
    """Whether `Authorization` is `Bearer <expected>`, compared in constant time."""
    return secrets.compare_digest((authorization or "").encode(), f"Bearer {expected}".encode())


LAPTOP, COORDINATOR, FAMILY = "laptop", "coordinator", "family"


@dataclass(frozen=True)
class AgentToken:
    """Whose bearer token this is: the shared agent token (`CHECKIN_TOKEN`, the base laptop and the
    droid), the Fetch.ai coordinator's, or a family agent's, which speaks for `contact_id`."""

    kind: Literal["laptop", "coordinator", "family"]
    contact_id: str | None = None


def agent_token(authorization: str | None) -> AgentToken | None:
    """The agent behind `Authorization`, or None when it carries no agent token."""
    settings = get_settings()
    for contact_id, token in settings.family_agent_tokens.items():
        if token and _is_checkin_token(authorization, token):
            return AgentToken(FAMILY, str(contact_id))
    if settings.coordinator_token and _is_checkin_token(authorization, settings.coordinator_token):
        return AgentToken(COORDINATOR)
    if settings.checkin_token and _is_checkin_token(authorization, settings.checkin_token):
        return AgentToken(LAPTOP)
    return None


def _require_agent(authorization: str | None, kinds: set[str]) -> None:
    """503 when no agent token is configured, 401 without a valid one, 403 for an agent of another kind."""
    settings = get_settings()
    if not (settings.checkin_token or settings.coordinator_token or settings.family_agent_tokens):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=CHECKIN_TOKEN_NOT_CONFIGURED)
    token = agent_token(authorization)
    if token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=NOT_AN_AGENT,
                            headers={"WWW-Authenticate": "Bearer"})
    if token.kind not in kinds:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_AN_AGENT)


def require_coordinator(authorization: Annotated[str | None, Header()] = None) -> None:
    """The watch roster's writes: the coordinator, or the shared agent token until it has its own."""
    _require_agent(authorization, {COORDINATOR} if get_settings().coordinator_token else {LAPTOP})


def require_roster_reader(authorization: Annotated[str | None, Header()] = None) -> None:
    """Reading the watch roster (names, on call, quiet hours): any of the pillow's agents."""
    _require_agent(authorization, {LAPTOP, COORDINATOR, FAMILY})


def require_checkin_token(authorization: Annotated[str | None, Header()] = None) -> None:
    """Only the base laptop may report a check-in result (it can cancel or start an escalation)."""
    expected = get_settings().checkin_token
    if not expected:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=CHECKIN_TOKEN_NOT_CONFIGURED)
    if not _is_checkin_token(authorization, expected):
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


async def require_role(db: AsyncClient, user_id: str, resident_id: str, *, owner: bool) -> dict[str, Any]:
    """The login's link to this resident (role, contact_id); 403 unless their contact looks after
    her (as the owner, when `owner`)."""
    link = await get_link_for_user(db, user_id, resident_id)
    if link is None or (owner and link["role"] != OWNER_ROLE):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_OWNER if link else NOT_LINKED)
    return link


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


@dataclass(frozen=True)
class ResidentLogin:
    """A signed-in member of the care circle of the resident in the path: her row, their contact id
    and whether they are her owner."""

    resident: dict[str, Any]
    contact_id: str
    is_owner: bool


async def resident_login(
    user_id: UserIdDep, resident: Annotated[dict[str, Any], Depends(existing_resident)], db: SupabaseDep
) -> ResidentLogin:
    """The resident in the path, for a login that looks after them, with who that login is."""
    link = await require_role(db, user_id, resident["id"], owner=False)
    return ResidentLogin(
        resident=resident, contact_id=link["contact_id"], is_owner=link["role"] == OWNER_ROLE
    )


ResidentLoginDep = Annotated[ResidentLogin, Depends(resident_login)]


def get_cartesia(request: Request) -> Cartesia:
    """Return the process-wide Cartesia client, or 503 when the server has no Cartesia key."""
    cartesia = request.app.state.cartesia
    if cartesia is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=VOICE_NOT_CONFIGURED)
    return cartesia


CartesiaDep = Annotated[Cartesia, Depends(get_cartesia)]


async def clone_upload(
    clip: UploadFile,
    name: Annotated[str, Form(min_length=1, max_length=CLONE_NAME_MAX)],
    consent: Annotated[str, Form()],
) -> CloneUpload:
    """The multipart recording to clone: an audio file (422 otherwise) of at most 10 MB (413), and
    `consent` "true" from the person recorded (422 otherwise)."""
    if consent != CONSENT_GIVEN:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=CONSENT_MISSING)
    if not name.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=CLONE_NAME_MISSING)
    if clip.content_type not in CLIP_CONTENT_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=CLIP_WRONG_TYPE)
    content = await clip.read(CLIP_MAX_BYTES + 1)
    if not content:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=CLIP_EMPTY)
    if len(content) > CLIP_MAX_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail=CLIP_TOO_LARGE)
    return CloneUpload(
        clip=content, filename=clip.filename or "clip", content_type=clip.content_type, name=name.strip()
    )


CloneUploadDep = Annotated[CloneUpload, Depends(clone_upload)]


@dataclass(frozen=True)
class Caller:
    """Who calls, before the pillow is read: a login (`user_id`), the family agent with the
    agent token speaking for `contact_id`, or the base laptop with the agent token speaking for
    her (`resident`, the talk key)."""

    user_id: str | None = None
    contact_id: str | None = None
    resident: bool = False


async def care_caller(
    db: SupabaseDep,
    authorization: Annotated[str | None, Header()] = None,
    contact_id: Annotated[
        UUID | None, Query(description="With the agent token: the contact it acts for")
    ] = None,
    as_: Annotated[
        Literal["resident"] | None, Query(alias="as", description="With the agent token: act for her")
    ] = None,
) -> Caller:
    """A family agent with its own token, for its own contact (403 if `contact_id` names another);
    the shared agent token with `?as=resident` for her (the base laptop's talk key); until the
    family agents have their own tokens, the shared agent token for the `contact_id` it names (422
    without one). Anyone else is the app's login, 401 without a valid one. A login's `contact_id`
    is ignored."""
    token = agent_token(authorization)
    if token is not None and token.kind == FAMILY:
        if contact_id is not None and str(contact_id) != token.contact_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=AGENT_CONTACT_MISMATCH)
        return Caller(contact_id=token.contact_id)
    if token is not None and token.kind == LAPTOP:
        if as_ == AS_RESIDENT:
            return Caller(resident=True)
        if get_settings().family_agent_tokens:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=AGENT_OWN_TOKEN)
        if contact_id is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=AGENT_CONTACT_MISSING)
        return Caller(contact_id=str(contact_id))
    return Caller(user_id=await current_user_id(db, authorization))


@dataclass(frozen=True)
class CareActor:
    """A member of the pillow's resident's care circle: her row and their contact id. `agent` is
    the agent acting for them (with `contact_name`, for its log), None when they signed in."""

    resident: dict[str, Any]
    contact_id: str | None  # None: she asked herself (the talk key)
    agent: str | None = None
    contact_name: str | None = None


async def pillow_care_actor(
    caller: Annotated[Caller, Depends(care_caller)], resident: ResidentDep, db: SupabaseDep
) -> CareActor:
    """Who acts on the resident of the pillow in the path: a login that looks after her (owner or
    contact), or the family agent for a contact of hers. 403 when they don't look after her."""
    if caller.resident:
        return CareActor(resident=resident, contact_id=None, agent=PILLOW_VOICE_AGENT,
                         contact_name=resident["preferred_name"])
    if caller.user_id is not None:
        link = await require_role(db, caller.user_id, resident["id"], owner=False)
        return CareActor(resident=resident, contact_id=link["contact_id"])
    link = await get_link_for_contact(db, caller.contact_id, resident["id"])
    if link is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=AGENT_CONTACT_NOT_LINKED)
    return CareActor(
        resident=resident,
        contact_id=link["contact_id"],
        agent=FAMILY_AGENT,
        contact_name=link["contacts"]["full_name"],
    )


CareActorDep = Annotated[CareActor, Depends(pillow_care_actor)]


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
