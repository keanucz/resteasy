"""Contact router: what a carer (an app user) can see."""

from uuid import UUID

from fastapi import APIRouter

from app.core.dependencies import SupabaseDep
from app.crud.pillows import list_pillows_for_contact
from app.schemas.pillow import Pillow

router = APIRouter(prefix="/contacts/{contact_id}", tags=["contacts"])


@router.get("/pillows")
async def list_contact_pillows(contact_id: UUID, db: SupabaseDep) -> list[Pillow]:
    """Return the pillows of every resident this contact looks after."""
    return await list_pillows_for_contact(db, contact_id)
