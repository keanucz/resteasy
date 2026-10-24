"""Supabase table names, so no query spells one out by hand."""

PILLOWS_TABLE = "pillows"
PILLOW_STATE_TABLE = "pillow_state"
COMMANDS_TABLE = "commands"
RESIDENT_CONTACTS_TABLE = "resident_contacts"
CONTACTS_TABLE = "contacts"
RESIDENTS_TABLE = "residents"
EVENTS_TABLE = "events"
NIGHT_TRIPS_VIEW = "night_trips"  # each bed_exit paired with the next bed_return
INCIDENTS_TABLE = "incidents"
NOTIFICATIONS_TABLE = "notifications"
AGENT_LOG_TABLE = "agent_log"
REMINDERS_TABLE = "reminders"
REMINDER_OCCURRENCES_TABLE = "reminder_occurrences"

# Conflict target that makes creating a reminder's occurrence for a due time idempotent
OCCURRENCE_KEY = "reminder_id,due_at"

# Conflict target for the one-row-per-pillow upsert into pillow_state
PILLOW_STATE_KEY = "pillow_id"

# Columns the device receives for each queued command (the CONTRACT.md command shape)
COMMAND_COLUMNS = "id, cmd, args"

# Supabase Storage bucket for residents' profile photos, one each at `<resident_id>/<PHOTO_FILE>`
RESIDENT_PHOTOS_BUCKET = "resident-photos"
PHOTO_FILE = "photo.jpg"
# Query parameter on the photo's public link: when it last changed (ms since epoch), to bust caches
PHOTO_VERSION_PARAM = "v"
