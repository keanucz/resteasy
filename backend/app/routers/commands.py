"""Command router: the app and agents queue commands, the device polls for them."""

from fastapi import APIRouter, Query, status

from app.core.dependencies import PillowDep, SupabaseDep
from app.crud.commands import list_commands_after, queue_command
from app.schemas.command import Command, CommandCreate

router = APIRouter(prefix="/pillows/{pillow_id}/commands", tags=["commands"])


@router.get("")
async def poll_commands(
    pillow: PillowDep, db: SupabaseDep, after: int = Query(default=0, ge=0)
) -> list[Command]:
    """Return commands newer than `after`, oldest first (CONTRACT.md section 3)."""
    return await list_commands_after(db, pillow.id, after)


@router.post("", status_code=status.HTTP_201_CREATED)
async def send_command(pillow: PillowDep, command: CommandCreate, db: SupabaseDep) -> Command:
    """Queue a command for the pillow to pick up on its next poll."""
    return await queue_command(db, pillow.id, command)
