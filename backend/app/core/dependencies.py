"""FastAPI dependencies shared across routers."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from supabase import AsyncClient

from app.core.app_constants import SUPABASE_NOT_CONFIGURED
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
