"""Data access for the command queue each pillow polls."""

from supabase import AsyncClient

from app.crud.crud_constants import COMMAND_COLUMNS, COMMANDS_TABLE
from app.schemas.command import Command, CommandCreate


async def queue_command(db: AsyncClient, pillow_id: str, command: CommandCreate) -> Command:
    """Append a command to the pillow's queue and return it with its new id."""
    row = {"pillow_id": pillow_id, **command.model_dump(mode="json")}
    response = await db.table(COMMANDS_TABLE).insert(row).execute()
    return Command(**response.data[0])


async def list_commands_after(db: AsyncClient, pillow_id: str, after: int) -> list[Command]:
    """Return the pillow's commands with an id above `after`, oldest first."""
    response = await (
        db.table(COMMANDS_TABLE)
        .select(COMMAND_COLUMNS)
        .eq("pillow_id", pillow_id)
        .gt("id", after)
        .order("id")
        .execute()
    )
    return [Command(**row) for row in response.data]
