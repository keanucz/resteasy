"""Supabase table names, so no query spells one out by hand."""

PILLOWS_TABLE = "pillows"
PILLOW_STATE_TABLE = "pillow_state"
COMMANDS_TABLE = "commands"
RESIDENT_CONTACTS_TABLE = "resident_contacts"
RESIDENTS_TABLE = "residents"
EVENTS_TABLE = "events"
INCIDENTS_TABLE = "incidents"
NOTIFICATIONS_TABLE = "notifications"
AGENT_LOG_TABLE = "agent_log"

# Conflict target for the one-row-per-pillow upsert into pillow_state
PILLOW_STATE_KEY = "pillow_id"

# Columns the device receives for each queued command (the CONTRACT.md command shape)
COMMAND_COLUMNS = "id, cmd, args"
